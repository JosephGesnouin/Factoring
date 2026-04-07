"""
Layer C6 - Human Review Intelligence
Prioritized review queue, structured feedback capture, and learning loop.

Components:
  C6.1 - Queue prioritization algorithm
  C6.2 - Review interface data (information to display)
  C6.3 - Structured feedback capture
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .config import C6Config
from .models import Invoice, MatchMethod, MatchResult, Payment, ReconciliationContext

logger = logging.getLogger(__name__)


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CORRECT = "CORRECT"
    SPLIT = "SPLIT"
    DEFER = "DEFER"
    ESCALATE = "ESCALATE"


@dataclass
class ReviewFeedback:
    """Structured feedback from human reviewer."""
    payment_id: str
    reviewer_id: str
    decision: ReviewDecision
    correct_invoice_refs: list[str] = field(default_factory=list)
    correct_allocation: dict[str, float] = field(default_factory=dict)
    rejection_reason: str = ""
    correction_notes: str = ""
    time_spent_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)


@dataclass
class ReviewItem:
    """Item in the human review queue with priority score."""
    context: ReconciliationContext
    priority_score: float = 0.0
    assigned_to: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    sla_deadline: datetime | None = None
    feedback: ReviewFeedback | None = None

    @property
    def payment(self) -> Payment:
        return self.context.payment

    @property
    def best_candidate(self) -> MatchResult | None:
        if self.context.candidate_matches:
            return max(self.context.candidate_matches, key=lambda m: m.confidence)
        return None


class HumanReviewQueue:
    """
    Layer C6: Intelligent human review queue.
    Prioritizes items by amount, age, confidence gap, and debtor risk.
    """

    def __init__(self, config: C6Config | None = None):
        self.config = config or C6Config()
        self._queue: list[ReviewItem] = []
        self._completed: list[ReviewItem] = []

    def enqueue(self, context: ReconciliationContext) -> ReviewItem:
        """Add an unresolved payment to the review queue."""
        item = ReviewItem(context=context)
        item.priority_score = self._compute_priority(item)
        item.sla_deadline = (
            item.created_at + timedelta(hours=self.config.sla_hours)
        ) if self.config.sla_hours > 0 else None

        self._queue.append(item)
        self._queue.sort(key=lambda x: x.priority_score, reverse=True)

        logger.info(
            "C6 enqueue: payment=%s priority=%.2f queue_size=%d",
            context.payment.id, item.priority_score, len(self._queue),
        )
        return item

    def get_next(self, reviewer_id: str | None = None) -> ReviewItem | None:
        """Get highest priority unassigned item."""
        for item in self._queue:
            if item.assigned_to is None or item.assigned_to == reviewer_id:
                item.assigned_to = reviewer_id
                return item
        return None

    def submit_feedback(self, payment_id: str, feedback: ReviewFeedback) -> MatchResult | None:
        """Process reviewer feedback and generate final match result."""
        item = next((i for i in self._queue if i.payment.id == payment_id), None)
        if not item:
            logger.warning("Payment %s not found in review queue", payment_id)
            return None

        item.feedback = feedback
        self._queue.remove(item)
        self._completed.append(item)

        if feedback.decision == ReviewDecision.APPROVE and item.best_candidate:
            result = item.best_candidate
            result.confidence = 1.0
            result.method = MatchMethod.C6_HUMAN
            result.flags.append("HUMAN_APPROVED")
            return result

        if feedback.decision == ReviewDecision.CORRECT:
            invoices = [
                inv for inv in item.context.open_invoices
                if inv.reference in feedback.correct_invoice_refs
            ]
            if invoices:
                return MatchResult(
                    payment_id=payment_id,
                    invoices=invoices,
                    method=MatchMethod.C6_HUMAN,
                    confidence=1.0,
                    allocated=feedback.correct_allocation,
                    flags=["HUMAN_CORRECTED"],
                    explanation=feedback.correction_notes,
                    rule_id="R-HUMAN",
                )

        if feedback.decision == ReviewDecision.REJECT:
            logger.info("Payment %s rejected by reviewer: %s", payment_id, feedback.rejection_reason)

        return None

    def get_review_data(self, item: ReviewItem) -> dict[str, Any]:
        """C6.2: Prepare all information for the review interface."""
        payment = item.payment
        context = item.context
        best = item.best_candidate

        return {
            "payment": {
                "id": payment.id,
                "amount": payment.amount,
                "currency": payment.currency.value,
                "date": str(payment.date),
                "label_raw": payment.label_raw,
                "label_normalized": payment.label_normalized,
                "debtor": payment.debtor.name if payment.debtor else "Unknown",
                "iban": payment.iban_source,
            },
            "signals": {
                "refs": payment.signals.raw_refs,
                "amounts": payment.signals.label_amounts,
                "periods": payment.signals.label_periods,
                "keywords": payment.signals.keywords,
                "label_class": payment.signals.label_class.value,
                "quality": payment.signals.label_quality,
            },
            "candidates": [
                {
                    "invoices": [inv.reference for inv in c.invoices],
                    "method": c.method.value,
                    "confidence": c.confidence,
                    "flags": c.flags,
                    "explanation": c.explanation,
                    "allocated": c.allocated,
                }
                for c in context.candidate_matches
            ],
            "best_candidate": {
                "invoices": [inv.reference for inv in best.invoices] if best else [],
                "confidence": best.confidence if best else 0,
                "method": best.method.value if best else None,
            },
            "open_invoices": [
                {
                    "ref": inv.reference,
                    "amount": inv.amount,
                    "issue_date": str(inv.issue_date),
                    "due_date": str(inv.due_date),
                }
                for inv in context.open_invoices[:50]
            ],
            "layers_attempted": context.layers_attempted,
            "priority": item.priority_score,
            "sla_deadline": str(item.sla_deadline) if item.sla_deadline else None,
        }

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def stats(self) -> dict[str, Any]:
        total_completed = len(self._completed)
        if total_completed == 0:
            return {"queue_size": len(self._queue), "completed": 0}

        approved = sum(1 for i in self._completed if i.feedback and i.feedback.decision == ReviewDecision.APPROVE)
        corrected = sum(1 for i in self._completed if i.feedback and i.feedback.decision == ReviewDecision.CORRECT)
        rejected = sum(1 for i in self._completed if i.feedback and i.feedback.decision == ReviewDecision.REJECT)
        avg_time = sum(
            i.feedback.time_spent_seconds for i in self._completed if i.feedback
        ) / max(total_completed, 1)

        return {
            "queue_size": len(self._queue),
            "completed": total_completed,
            "approved": approved,
            "corrected": corrected,
            "rejected": rejected,
            "approval_rate": approved / total_completed,
            "avg_review_time_seconds": avg_time,
        }

    # -----------------------------------------------------------------------
    # C6.1 — Priority Algorithm
    # -----------------------------------------------------------------------
    def _compute_priority(self, item: ReviewItem) -> float:
        """
        Compute priority score for queue ordering.
        Higher score = reviewed first.
        Weighted combination of: amount, age, confidence gap, debtor risk.
        """
        weights = self.config.priority_weights
        payment = item.payment
        best = item.best_candidate

        # Amount factor (normalized, higher amounts first)
        amount_score = min(payment.amount / 100_000, 1.0)

        # Age factor (older unmatched payments have higher priority)
        if payment.date:
            age_days = (datetime.now().date() - payment.date).days
            age_score = min(age_days / 30, 1.0)
        else:
            age_score = 0.5

        # Confidence gap (closer to threshold = higher priority, easier to resolve)
        if best:
            gap = abs(best.confidence - 0.90)
            confidence_gap_score = 1.0 - min(gap / 0.5, 1.0)
        else:
            confidence_gap_score = 0.3

        # Debtor risk
        debtor_risk_score = payment.debtor.risk_score if payment.debtor else 0.5

        priority = (
            weights.get("amount", 0.3) * amount_score
            + weights.get("age", 0.25) * age_score
            + weights.get("confidence_gap", 0.25) * confidence_gap_score
            + weights.get("debtor_risk", 0.2) * debtor_risk_score
        )

        return priority
