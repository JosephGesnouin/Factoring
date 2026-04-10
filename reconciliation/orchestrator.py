"""
Global Orchestrator - End-to-End Pipeline
Manages the flow through all 6 layers with error handling,
timeouts, validation, and metrics collection.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .c0_preprocessing import PaymentPreprocessor
from .c1_exact_matching import ExactMatcher
from .c2_business_rules import BusinessRuleMatcher, DuplicateIndex
from .c3_nlp_fuzzy import NLPFuzzyMatcher
from .c4_ml import MLMatcher
from .c5_llm import LLMMatcher
from .c6_human_review import HumanReviewQueue
from .config import ReconciliationConfig
from .debtor_profiler import DebtorProfiler
from .models import (
    CreditNote,
    Debtor,
    DuplicateAlert,
    Invoice,
    MatchResult,
    Payment,
    ReconciliationContext,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Tracks pipeline performance metrics."""
    total_payments: int = 0
    matched_auto: int = 0
    matched_human: int = 0
    unmatched: int = 0
    errors: int = 0
    by_layer: dict[int, int] = field(default_factory=lambda: {i: 0 for i in range(7)})
    by_method: dict[str, int] = field(default_factory=dict)
    avg_processing_time_ms: float = 0.0
    total_processing_time_ms: float = 0.0
    duplicate_alerts: int = 0

    @property
    def auto_rate(self) -> float:
        if self.total_payments == 0:
            return 0.0
        return self.matched_auto / self.total_payments

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_payments": self.total_payments,
            "matched_auto": self.matched_auto,
            "matched_human": self.matched_human,
            "unmatched": self.unmatched,
            "errors": self.errors,
            "auto_rate": f"{self.auto_rate:.1%}",
            "avg_time_ms": f"{self.avg_processing_time_ms:.1f}",
            "by_layer": self.by_layer,
            "by_method": self.by_method,
            "duplicate_alerts": self.duplicate_alerts,
        }


class ReconciliationOrchestrator:
    """
    End-to-end reconciliation pipeline.
    Routes payments through C0→C1→C2→C3→C4→C5→C6 with
    early-exit on confident match and fallback to human review.
    """

    def __init__(self, config: ReconciliationConfig | None = None):
        self.config = config or ReconciliationConfig()
        self._preprocessor = PaymentPreprocessor(self.config.c0)
        self._exact_matcher = ExactMatcher(self.config.c1)
        self._business_matcher = BusinessRuleMatcher(self.config.c2)
        self._nlp_matcher = NLPFuzzyMatcher(self.config.c3)
        self._ml_matcher = MLMatcher(self.config.c4)
        self._llm_matcher = LLMMatcher(self.config.c5)
        self._review_queue = HumanReviewQueue(self.config.c6)
        self._debtor_profiler = DebtorProfiler()
        self._metrics = PipelineMetrics()
        # Use indexed duplicate detection (O(1) lookup) instead of linear scan.
        self._duplicate_index = DuplicateIndex(max_size=50_000)
        self._iban_debtor_map: dict[str, str] = {}
        self._debtor_lookup: dict[str, Debtor] = {}

    def setup(
        self,
        invoices: list[Invoice],
        debtors: list[Debtor] | None = None,
        iban_debtor_map: dict[str, str] | None = None,
    ) -> None:
        """Initialize indexes and lookups."""
        self._exact_matcher.build_index(invoices)
        self._nlp_matcher.build_index(invoices)

        if debtors:
            self._debtor_lookup = {d.id: d for d in debtors}
        if iban_debtor_map:
            self._iban_debtor_map = iban_debtor_map

    def process_payment(
        self, payment: Payment, open_invoices: list[Invoice]
    ) -> ReconciliationContext:
        """
        Process a single payment through the full pipeline.
        Returns the complete reconciliation context.
        """
        start_time = time.time()
        self._metrics.total_payments += 1

        ctx = ReconciliationContext(
            payment=payment,
            open_invoices=open_invoices,
            started_at=datetime.now(),
        )

        try:
            # ── C0: Preprocessing ──
            ctx = self._run_layer_c0(ctx)

            # ── Duplicate check (O(1) indexed lookup) ──
            duplicates = self._business_matcher.check_duplicates(
                payment, self._duplicate_index
            )
            if duplicates:
                self._metrics.duplicate_alerts += len(duplicates)
                for d in duplicates:
                    ctx.processing_log.append({"event": "DUPLICATE_ALERT", "detail": d.alert_type})
                    if d.alert_type == "EXACT_DUPLICATE":
                        logger.warning("Exact duplicate: %s ↔ %s", d.payment_id, d.duplicate_of)
            self._duplicate_index.add(payment)

            # ── C1: Exact matching ──
            result = self._run_layer(ctx, 1, lambda: self._exact_matcher.match(payment, open_invoices))
            if result and result.confidence >= self.config.orchestrator.auto_match_confidence_threshold:
                return self._finalize(ctx, result, start_time)

            # ── C2: Business rules ──
            result = self._run_layer(ctx, 2, lambda: self._business_matcher.match(payment, open_invoices))
            if result and result.confidence >= self.config.orchestrator.auto_match_confidence_threshold:
                return self._finalize(ctx, result, start_time)

            # ── C3: NLP/Fuzzy ──
            # C3 uses a lower auto-match threshold (0.80) because fuzzy scores
            # are inherently lower than deterministic C1/C2 scores.
            result = self._run_layer(ctx, 3, lambda: self._nlp_matcher.match(payment, open_invoices))
            c3_threshold = max(self.config.orchestrator.auto_match_confidence_threshold - 0.10, 0.80)
            if result and result.confidence >= c3_threshold:
                return self._finalize(ctx, result, start_time)

            # ── C4: ML ──
            # C4 uses its own confidence_threshold (default 0.85) since ML scores
            # are calibrated differently from deterministic rules.
            # Even when C4 can't auto-match, it always ranks candidates for C6 reco.
            if self._ml_matcher.is_trained:
                result = self._run_layer(ctx, 4, lambda: self._ml_matcher.match(payment, open_invoices))
                c4_threshold = self.config.c4.confidence_threshold
                if result and result.confidence >= c4_threshold:
                    return self._finalize(ctx, result, start_time)

                # Always compute ML rankings for C6 recommendations
                ctx.ml_rankings = self._ml_matcher.rank_candidates(payment, open_invoices, top_k=5)
            else:
                ctx.layers_attempted.append(4)
                ctx.processing_log.append({
                    "layer": 4, "time_ms": 0, "event": "SKIPPED",
                    "detail": "C4 model not trained (call MLMatcher.train() first)",
                })

            # ── C5: LLM ──
            result = self._run_layer(
                ctx, 5,
                lambda: self._llm_matcher.match(payment, open_invoices, ctx.candidate_matches),
            )
            if result and result.confidence >= self.config.orchestrator.auto_match_confidence_threshold:
                return self._finalize(ctx, result, start_time)

            # ── C6: Human review ──
            ctx.layers_attempted.append(6)
            self._review_queue.enqueue(ctx)
            self._metrics.unmatched += 1
            self._metrics.by_layer[6] = self._metrics.by_layer.get(6, 0) + 1

        except Exception as e:
            logger.error("Pipeline error for payment %s: %s", payment.id, e, exc_info=True)
            self._metrics.errors += 1
            ctx.processing_log.append({"event": "ERROR", "detail": str(e)})

        ctx.completed_at = datetime.now()
        elapsed = (time.time() - start_time) * 1000
        self._update_timing(elapsed)

        return ctx

    def process_batch(
        self,
        payments: list[Payment],
        open_invoices: list[Invoice],
        rebuild_every: int = 100,
    ) -> list[ReconciliationContext]:
        """Process a batch of payments.

        Rebuilds C1/C3 indexes every ``rebuild_every`` matches (default 100)
        to ensure consumed invoices are no longer visible to matchers.
        Without this rebuild, the hash index and TF-IDF matrix still
        contain already-matched invoices → stale lookups.
        """
        results = []
        matches_since_rebuild = 0
        dirty = False
        for payment in payments:
            ctx = self.process_payment(payment, open_invoices)
            results.append(ctx)
            if ctx.final_match:
                matched_ids = {inv.id for inv in ctx.final_match.invoices}
                open_invoices = [inv for inv in open_invoices if inv.id not in matched_ids]
                matches_since_rebuild += 1
                dirty = True
                if matches_since_rebuild >= rebuild_every:
                    self._exact_matcher.build_index(open_invoices)
                    self._nlp_matcher.build_index(open_invoices)
                    matches_since_rebuild = 0
                    dirty = False

        # Final rebuild so subsequent calls see fresh state
        if dirty:
            self._exact_matcher.build_index(open_invoices)
            self._nlp_matcher.build_index(open_invoices)

        return results

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    @property
    def debtor_profiler(self) -> DebtorProfiler:
        return self._debtor_profiler

    @property
    def review_queue(self) -> HumanReviewQueue:
        return self._review_queue

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------
    def _run_layer_c0(self, ctx: ReconciliationContext) -> ReconciliationContext:
        """Run C0 preprocessing."""
        ctx.layers_attempted.append(0)
        start = time.time()
        ctx.payment = self._preprocessor.process(
            ctx.payment,
            debtor_lookup=self._debtor_lookup,
            iban_debtor_map=self._iban_debtor_map,
        )
        elapsed = (time.time() - start) * 1000
        ctx.processing_log.append({"layer": 0, "time_ms": elapsed, "event": "PREPROCESSED"})

        # Enrich debtor context
        if ctx.payment.debtor:
            ctx.debtor = ctx.payment.debtor
            ctx.open_credits = list(ctx.payment.debtor.open_credits)

        return ctx

    def _run_layer(self, ctx: ReconciliationContext, layer: int, fn) -> MatchResult | None:
        """Run a matching layer with timing and error handling."""
        ctx.layers_attempted.append(layer)
        start = time.time()

        try:
            result = fn()
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error("Layer C%d error: %s", layer, e, exc_info=True)
            ctx.processing_log.append({
                "layer": layer, "time_ms": elapsed, "event": "ERROR", "detail": str(e),
            })
            return None

        elapsed = (time.time() - start) * 1000

        if result:
            result.layer = layer
            result.processing_time_ms = elapsed

            # Apply debtor behavior boost/penalty to confidence
            boost = self._debtor_profiler.confidence_boost(ctx.payment, result)
            if boost != 0.0:
                result.confidence = max(0.0, min(1.0, result.confidence + boost))
                if boost > 0:
                    result.flags.append(f"DEBTOR_BOOST_{boost:+.2f}")
                else:
                    result.flags.append(f"DEBTOR_PENALTY_{boost:+.2f}")

            ctx.candidate_matches.append(result)
            ctx.processing_log.append({
                "layer": layer,
                "time_ms": elapsed,
                "event": "MATCH_FOUND",
                "method": result.method.value,
                "confidence": result.confidence,
            })
        else:
            ctx.processing_log.append({
                "layer": layer, "time_ms": elapsed, "event": "NO_MATCH",
            })

        return result

    def _finalize(
        self, ctx: ReconciliationContext, result: MatchResult, start_time: float
    ) -> ReconciliationContext:
        """Finalize a successful match."""
        ctx.final_match = result
        ctx.completed_at = datetime.now()

        elapsed = (time.time() - start_time) * 1000
        self._update_timing(elapsed)

        self._metrics.matched_auto += 1
        self._metrics.by_layer[result.layer] = self._metrics.by_layer.get(result.layer, 0) + 1
        method_key = result.method.value
        self._metrics.by_method[method_key] = self._metrics.by_method.get(method_key, 0) + 1

        logger.info(
            "Payment %s matched: layer=C%d method=%s confidence=%.2f time=%.1fms",
            ctx.payment.id, result.layer, result.method.value, result.confidence, elapsed,
        )
        return ctx

    def _update_timing(self, elapsed_ms: float) -> None:
        self._metrics.total_processing_time_ms += elapsed_ms
        self._metrics.avg_processing_time_ms = (
            self._metrics.total_processing_time_ms / self._metrics.total_payments
        )
