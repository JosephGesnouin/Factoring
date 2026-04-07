"""Tests for the Global Orchestrator."""

import pytest
from datetime import date

from reconciliation.config import ReconciliationConfig
from reconciliation.models import (
    Debtor,
    Invoice,
    MatchMethod,
    Payment,
    PaymentSignals,
)
from reconciliation.orchestrator import ReconciliationOrchestrator


def make_invoice(ref="FAC001", amount=10000.0, debtor_id="D1"):
    return Invoice(
        id=f"INV-{ref}", reference=ref, debtor_id=debtor_id,
        amount=amount, amount_ht=amount / 1.20,
        issue_date=date(2024, 9, 1), due_date=date(2024, 10, 1),
    )


def make_payment(amount=10000.0, debtor_id="D1", label="FAC001", refs=None):
    return Payment(
        id="PAY-001", amount=amount, debtor_id=debtor_id,
        date=date(2024, 10, 15),
        label_raw=label, label_normalized=label.upper(),
        signals=PaymentSignals(raw_refs=refs or []),
    )


class TestOrchestratorPipeline:
    def test_c1_exact_match(self):
        orch = ReconciliationOrchestrator()
        inv = make_invoice("FAC001", 10000.0)
        payment = make_payment(10000.0, refs=["FAC001"])
        orch.setup([inv])

        ctx = orch.process_payment(payment, [inv])
        assert ctx.final_match is not None
        assert ctx.final_match.confidence >= 0.97
        assert ctx.final_match.layer == 1

    def test_c2_tolerance_match(self):
        orch = ReconciliationOrchestrator()
        inv = make_invoice("FAC001", 10000.50)
        payment = make_payment(10000.0, refs=[])  # No ref, but rounding tolerance
        orch.setup([inv])

        ctx = orch.process_payment(payment, [inv])
        assert ctx.final_match is not None
        assert ctx.final_match.layer == 2

    def test_fallback_to_review_queue(self):
        orch = ReconciliationOrchestrator()
        inv = make_invoice("FAC001", 10000.0)
        # Payment with no refs, completely different amount
        payment = make_payment(999.99, refs=[], label="UNKNOWN")
        payment.label_normalized = "UNKNOWN"
        payment.signals = PaymentSignals()
        orch.setup([inv])

        ctx = orch.process_payment(payment, [inv])
        # Should end up in review queue (no confident match)
        assert 6 in ctx.layers_attempted
        assert orch.review_queue.queue_size >= 1

    def test_batch_processing(self):
        orch = ReconciliationOrchestrator()
        inv1 = make_invoice("FAC001", 5000.0)
        inv2 = make_invoice("FAC002", 3000.0)
        p1 = make_payment(5000.0, refs=["FAC001"])
        p1.id = "PAY-001"
        p2 = make_payment(3000.0, refs=["FAC002"])
        p2.id = "PAY-002"
        orch.setup([inv1, inv2])

        results = orch.process_batch([p1, p2], [inv1, inv2])
        assert len(results) == 2
        assert results[0].final_match is not None
        assert results[1].final_match is not None

    def test_metrics_tracking(self):
        orch = ReconciliationOrchestrator()
        inv = make_invoice("FAC001", 10000.0)
        payment = make_payment(10000.0, refs=["FAC001"])
        orch.setup([inv])

        orch.process_payment(payment, [inv])

        assert orch.metrics.total_payments == 1
        assert orch.metrics.matched_auto == 1
        assert orch.metrics.auto_rate == 1.0


class TestOrchestratorEdgeCases:
    def test_empty_invoices(self):
        orch = ReconciliationOrchestrator()
        payment = make_payment(10000.0, refs=["FAC001"])
        orch.setup([])

        ctx = orch.process_payment(payment, [])
        # No invoices → can't match, goes to review
        assert ctx.final_match is None

    def test_preprocessing_applied(self):
        orch = ReconciliationOrchestrator()
        inv = make_invoice("FAC001", 10000.0)
        payment = Payment(
            id="PAY-001", amount=10000.0, debtor_id="D1",
            date=date(2024, 10, 15),
            label_raw="fac-001 reglement",
        )
        payment.signals = PaymentSignals(raw_refs=["FAC001"])
        orch.setup([inv])

        ctx = orch.process_payment(payment, [inv])
        # C0 should have normalized the label
        assert ctx.payment.label_normalized != ""
