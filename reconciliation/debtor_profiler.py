"""
Debtor Behavior Profiler — Learns payment patterns per debtor.

Analyzes historical payment-invoice pairs to build a behavioral profile
for each debtor. The profile is then used to:
  1. Boost confidence of matches that fit the debtor's pattern
  2. Suggest the most likely invoice(s) when no ref is available
  3. Detect anomalies (unusual amount, timing, or payment method)

Learned features per debtor:
  - Typical payment day(s) of month
  - Average delay vs due date
  - Usual number of invoices per payment
  - Preferred payment method (exact ref, grouped, subset sum, etc.)
  - Typical amount range
  - Discount/retention patterns
  - Label language and style
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .models import Invoice, MatchResult, Payment, ReconciliationContext

logger = logging.getLogger(__name__)


@dataclass
class DebtorBehavior:
    """Learned behavioral profile for one debtor."""
    debtor_id: str
    debtor_name: str = ""
    n_payments: int = 0

    # Timing
    avg_delay_days: float = 0.0
    typical_pay_days: list[int] = field(default_factory=list)  # e.g. [15, 28]
    pay_day_regularity: float = 0.0  # 0=random, 1=always same day

    # Amounts
    avg_amount: float = 0.0
    min_amount: float = 0.0
    max_amount: float = 0.0
    amount_stddev: float = 0.0

    # Invoice count per payment
    avg_invoices_per_payment: float = 1.0
    max_invoices_per_payment: int = 1
    pct_multi_invoice: float = 0.0  # % of payments covering >1 invoice

    # Methods
    method_distribution: dict[str, float] = field(default_factory=dict)
    preferred_method: str = ""
    pct_with_ref: float = 0.0  # % of payments with structured ref

    # Tolerance patterns
    pct_with_discount: float = 0.0
    pct_with_retention: float = 0.0
    pct_with_fees: float = 0.0
    pct_with_credit_note: float = 0.0

    # Layer distribution
    layer_distribution: dict[str, float] = field(default_factory=dict)
    auto_rate: float = 0.0

    # Anomaly thresholds (2 sigma)
    amount_upper_bound: float = 0.0
    amount_lower_bound: float = 0.0
    delay_upper_bound: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "debtor_id": self.debtor_id,
            "debtor_name": self.debtor_name,
            "n_payments": self.n_payments,
            "avg_delay_days": round(self.avg_delay_days, 1),
            "typical_pay_days": self.typical_pay_days,
            "pay_day_regularity": round(self.pay_day_regularity, 2),
            "avg_amount": round(self.avg_amount, 2),
            "min_amount": round(self.min_amount, 2),
            "max_amount": round(self.max_amount, 2),
            "avg_invoices_per_payment": round(self.avg_invoices_per_payment, 1),
            "max_invoices_per_payment": self.max_invoices_per_payment,
            "pct_multi_invoice": round(self.pct_multi_invoice * 100, 1),
            "preferred_method": self.preferred_method,
            "pct_with_ref": round(self.pct_with_ref * 100, 1),
            "pct_with_discount": round(self.pct_with_discount * 100, 1),
            "pct_with_retention": round(self.pct_with_retention * 100, 1),
            "auto_rate": round(self.auto_rate * 100, 1),
            "method_distribution": {k: round(v*100, 1) for k, v in self.method_distribution.items()},
            "layer_distribution": {k: round(v*100, 1) for k, v in self.layer_distribution.items()},
        }


class DebtorProfiler:
    """Learns and stores behavioral profiles for all debtors.

    Usage:
        profiler = DebtorProfiler()
        profiler.learn(results)  # learn from historical reconciliation results
        profile = profiler.get("D01")  # get profile for debtor D01
        boost = profiler.confidence_boost(payment, candidate_match)  # score adjustment
    """

    def __init__(self):
        self._profiles: dict[str, DebtorBehavior] = {}

    def learn(self, results: list[ReconciliationContext]) -> None:
        """Learn debtor behaviors from a batch of reconciliation results."""
        # Group results by debtor
        by_debtor: dict[str, list[ReconciliationContext]] = defaultdict(list)
        for ctx in results:
            did = ctx.payment.debtor_id
            if did:
                by_debtor[did].append(ctx)

        for did, ctxs in by_debtor.items():
            self._profiles[did] = self._build_profile(did, ctxs)

        logger.info("DebtorProfiler: learned %d debtor profiles from %d results",
                     len(self._profiles), len(results))

    def get(self, debtor_id: str) -> DebtorBehavior | None:
        return self._profiles.get(debtor_id)

    @property
    def profiles(self) -> dict[str, DebtorBehavior]:
        return dict(self._profiles)

    def confidence_boost(self, payment: Payment, match: MatchResult) -> float:
        """Compute a confidence adjustment based on debtor behavior fit.

        Returns a value in [-0.10, +0.10] that should be ADDED to the
        match confidence. Positive = payment fits the debtor's pattern,
        negative = anomaly.
        """
        profile = self._profiles.get(payment.debtor_id or "")
        if not profile or profile.n_payments < 5:
            return 0.0

        boost = 0.0
        n_signals = 0

        # 1. Method fit: does this match method match the debtor's preferred method?
        if match.method.value in profile.method_distribution:
            method_pct = profile.method_distribution[match.method.value]
            if method_pct > 0.3:
                boost += 0.03  # common method for this debtor
                n_signals += 1
            elif method_pct < 0.05:
                boost -= 0.02  # unusual method
                n_signals += 1

        # 2. Amount fit: is the payment amount in the debtor's usual range?
        if profile.amount_upper_bound > 0:
            if profile.amount_lower_bound <= payment.amount <= profile.amount_upper_bound:
                boost += 0.02
                n_signals += 1
            elif payment.amount > profile.amount_upper_bound * 1.5:
                boost -= 0.03  # unusually large
                n_signals += 1

        # 3. Invoice count fit
        n_inv = len(match.invoices)
        if abs(n_inv - profile.avg_invoices_per_payment) <= 1:
            boost += 0.02
            n_signals += 1
        elif n_inv > profile.max_invoices_per_payment * 2:
            boost -= 0.02
            n_signals += 1

        # 4. Timing fit: does the payment date match the debtor's pattern?
        if payment.date and profile.typical_pay_days:
            day = payment.date.day
            if day in profile.typical_pay_days or any(abs(day - d) <= 2 for d in profile.typical_pay_days):
                boost += 0.02
                n_signals += 1

        # 5. Tolerance pattern: does the flag match known patterns?
        if match.flags:
            flags_set = set(match.flags)
            if "DISCOUNT_APPLIED" in flags_set and profile.pct_with_discount > 0.1:
                boost += 0.02
                n_signals += 1
            if "RETENTION" in " ".join(match.flags) and profile.pct_with_retention > 0.1:
                boost += 0.02
                n_signals += 1
            if "SWIFT" in " ".join(match.flags) and profile.pct_with_fees > 0.1:
                boost += 0.02
                n_signals += 1

        return max(-0.10, min(0.10, boost))

    def is_anomaly(self, payment: Payment) -> tuple[bool, list[str]]:
        """Check if a payment is anomalous for this debtor."""
        profile = self._profiles.get(payment.debtor_id or "")
        if not profile or profile.n_payments < 10:
            return False, []

        anomalies = []

        if profile.amount_upper_bound > 0 and payment.amount > profile.amount_upper_bound:
            anomalies.append(f"AMOUNT_HIGH: {payment.amount:,.2f} > usual max {profile.amount_upper_bound:,.2f}")

        if profile.amount_lower_bound > 0 and payment.amount < profile.amount_lower_bound * 0.5:
            anomalies.append(f"AMOUNT_LOW: {payment.amount:,.2f} < usual min {profile.amount_lower_bound:,.2f}")

        return len(anomalies) > 0, anomalies

    def suggest_invoices(
        self, payment: Payment, open_invoices: list[Invoice], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Suggest most likely invoices based on debtor behavior.

        Scores each invoice using the debtor's learned patterns:
          - Amount proximity to debtor's typical range
          - Temporal proximity to expected payment timing
          - Number of invoices typical for this debtor
        """
        profile = self._profiles.get(payment.debtor_id or "")
        if not profile:
            return []

        debtor_invs = [inv for inv in open_invoices
                       if inv.debtor_id == payment.debtor_id]
        if not debtor_invs:
            return []

        scored = []
        for inv in debtor_invs:
            score = 0.0
            reasons = []

            # Amount proximity
            if inv.amount > 0:
                diff_pct = abs(payment.amount - inv.amount) / inv.amount
                if diff_pct < 0.001:
                    score += 0.35; reasons.append("montant exact")
                elif diff_pct < 0.05:
                    score += 0.25; reasons.append(f"ecart {diff_pct:.1%}")
                elif diff_pct < 0.15:
                    score += 0.10

            # Temporal: is invoice due around now?
            if payment.date and inv.due_date:
                delay = (payment.date - inv.due_date).days
                expected_delay = profile.avg_delay_days
                if abs(delay - expected_delay) <= 5:
                    score += 0.25; reasons.append(f"delai attendu ({expected_delay:.0f}j)")
                elif abs(delay - expected_delay) <= 15:
                    score += 0.10; reasons.append(f"delai proche")

            # Multi-invoice: if debtor usually groups, try N-invoice combos
            if profile.avg_invoices_per_payment > 1.5:
                score += 0.05; reasons.append(f"debiteur groupe (avg {profile.avg_invoices_per_payment:.1f})")

            # Same debtor
            score += 0.20; reasons.append("meme debiteur")

            if score > 0.1:
                scored.append({
                    "invoice": inv,
                    "score": min(score, 1.0),
                    "reason": " | ".join(reasons),
                })

        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def _build_profile(self, debtor_id: str, ctxs: list[ReconciliationContext]) -> DebtorBehavior:
        profile = DebtorBehavior(debtor_id=debtor_id)
        profile.n_payments = len(ctxs)

        if not ctxs:
            return profile

        # Name
        for ctx in ctxs:
            if ctx.payment.debtor and ctx.payment.debtor.name:
                profile.debtor_name = ctx.payment.debtor.name
                break

        amounts = [ctx.payment.amount for ctx in ctxs]
        profile.avg_amount = sum(amounts) / len(amounts)
        profile.min_amount = min(amounts)
        profile.max_amount = max(amounts)

        if len(amounts) > 1:
            mean = profile.avg_amount
            variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            profile.amount_stddev = variance ** 0.5
            profile.amount_upper_bound = mean + 2 * profile.amount_stddev
            profile.amount_lower_bound = max(0, mean - 2 * profile.amount_stddev)

        # Timing
        pay_days = [ctx.payment.date.day for ctx in ctxs if ctx.payment.date]
        if pay_days:
            day_counts = Counter(pay_days)
            top_days = [d for d, c in day_counts.most_common(3) if c >= len(pay_days) * 0.15]
            profile.typical_pay_days = top_days

            if top_days:
                on_pattern = sum(1 for d in pay_days if any(abs(d - td) <= 2 for td in top_days))
                profile.pay_day_regularity = on_pattern / len(pay_days)

        # Delay vs due date
        delays = []
        for ctx in ctxs:
            if ctx.final_match and ctx.payment.date:
                for inv in ctx.final_match.invoices:
                    if inv.due_date:
                        delays.append((ctx.payment.date - inv.due_date).days)
        if delays:
            profile.avg_delay_days = sum(delays) / len(delays)
            if len(delays) > 1:
                mean_d = profile.avg_delay_days
                var_d = sum((d - mean_d) ** 2 for d in delays) / len(delays)
                profile.delay_upper_bound = mean_d + 2 * (var_d ** 0.5)

        # Invoice count per payment
        inv_counts = []
        for ctx in ctxs:
            if ctx.final_match:
                inv_counts.append(len(ctx.final_match.invoices))
        if inv_counts:
            profile.avg_invoices_per_payment = sum(inv_counts) / len(inv_counts)
            profile.max_invoices_per_payment = max(inv_counts)
            profile.pct_multi_invoice = sum(1 for c in inv_counts if c > 1) / len(inv_counts)

        # Methods
        methods = [ctx.final_match.method.value for ctx in ctxs if ctx.final_match]
        if methods:
            total_m = len(methods)
            method_counts = Counter(methods)
            profile.method_distribution = {m: c / total_m for m, c in method_counts.items()}
            profile.preferred_method = method_counts.most_common(1)[0][0]

        # Ref presence
        with_ref = sum(1 for ctx in ctxs if ctx.payment.signals.raw_refs)
        profile.pct_with_ref = with_ref / len(ctxs)

        # Tolerance flags
        all_flags = []
        for ctx in ctxs:
            if ctx.final_match and ctx.final_match.flags:
                all_flags.extend(ctx.final_match.flags)
        flag_str = " ".join(all_flags)
        profile.pct_with_discount = flag_str.count("DISCOUNT") / max(len(ctxs), 1)
        profile.pct_with_retention = flag_str.count("RETENTION") / max(len(ctxs), 1)
        profile.pct_with_fees = flag_str.count("SWIFT") / max(len(ctxs), 1)
        profile.pct_with_credit_note = flag_str.count("CREDIT") / max(len(ctxs), 1)

        # Layer distribution
        layers = [f"C{ctx.final_match.layer}" if ctx.final_match else "C6" for ctx in ctxs]
        layer_counts = Counter(layers)
        profile.layer_distribution = {l: c / len(layers) for l, c in layer_counts.items()}
        profile.auto_rate = sum(1 for ctx in ctxs if ctx.final_match) / len(ctxs)

        return profile
