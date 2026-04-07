"""Tests for Layer C2 - Advanced Business Rules."""

import pytest
from datetime import date

from reconciliation.c2_business_rules import BusinessRuleMatcher
from reconciliation.models import (
    CreditNote,
    Debtor,
    Invoice,
    MatchMethod,
    Payment,
    PaymentSignals,
)


def make_invoice(ref="FAC001", amount=10000.0, debtor_id="D1", **kwargs):
    defaults = {
        "issue_date": date(2024, 9, 1),
        "due_date": date(2024, 10, 1),
    }
    defaults.update(kwargs)
    return Invoice(
        id=f"INV-{ref}", reference=ref, debtor_id=debtor_id,
        amount=amount, amount_ht=amount / 1.20, **defaults,
    )


def make_payment(amount=10000.0, debtor_id="D1", debtor=None, **kwargs):
    return Payment(
        id="PAY-001", amount=amount, debtor_id=debtor_id,
        date=date(2024, 10, 15), label_raw="", label_normalized="",
        signals=PaymentSignals(), debtor=debtor, **kwargs,
    )


@pytest.fixture
def matcher():
    return BusinessRuleMatcher()


class TestAmountTolerance:
    """C2.1 - Amount tolerance rules."""

    def test_rounding_tolerance(self, matcher):
        inv = make_invoice(amount=10000.50)
        payment = make_payment(amount=10000.0)
        result = matcher.match(payment, [inv])
        assert result is not None
        assert "ROUNDING" in result.flags

    def test_swift_fees(self, matcher):
        debtor = Debtor(id="D1", name="Test", country="US")
        inv = make_invoice(amount=15000.0)
        payment = make_payment(amount=14972.0, debtor=debtor)
        result = matcher.match(payment, [inv])
        assert result is not None
        assert "SWIFT_FEES" in result.flags

    def test_contractual_discount(self, matcher):
        debtor = Debtor(id="D1", name="Test", discount_rate=0.02)
        inv = make_invoice(amount=10000.0)
        payment = make_payment(amount=9800.0, debtor=debtor)
        result = matcher.match(payment, [inv])
        assert result is not None
        assert "DISCOUNT_APPLIED" in result.flags

    def test_retention_btp(self, matcher):
        debtor = Debtor(id="D1", name="Test", sector="BTP")
        inv = make_invoice(amount=20000.0)
        payment = make_payment(amount=19000.0, debtor=debtor)  # 5% retention
        result = matcher.match(payment, [inv])
        assert result is not None
        assert "RETENTION_BTP" in result.flags


class TestCreditNotes:
    """C2.5 - Credit note deduction rules."""

    def test_exact_credit_deduction(self, matcher):
        credit = CreditNote(id="CN1", reference="AV001", debtor_id="D1", amount=500.0)
        debtor = Debtor(id="D1", name="Test", open_credits=[credit])
        inv = make_invoice(amount=10000.0)
        payment = make_payment(amount=9500.0, debtor=debtor)
        result = matcher.match(payment, [inv])
        assert result is not None
        assert any("CREDIT" in f for f in result.flags)


class TestSubsetSum:
    """C2.4 - Multi-invoice subset sum."""

    def test_two_sum(self, matcher):
        inv1 = make_invoice("FAC001", 5000.0)
        inv2 = make_invoice("FAC002", 3000.0)
        inv3 = make_invoice("FAC003", 7000.0)
        payment = make_payment(amount=8000.0)
        result = matcher.match(payment, [inv1, inv2, inv3])
        assert result is not None
        assert result.method == MatchMethod.C2_SUBSET_SUM
        total_allocated = sum(result.allocated.values())
        assert abs(total_allocated - 8000.0) < 0.01

    def test_greedy_subset(self, matcher):
        invs = [make_invoice(f"FAC{i:03d}", amount) for i, amount in
                enumerate([5000, 3000, 2000, 1500, 500])]
        payment = make_payment(amount=10500.0)
        result = matcher.match(payment, invs)
        assert result is not None
        assert result.method == MatchMethod.C2_SUBSET_SUM


class TestDuplicateDetection:
    """C2.8 - Anti-duplicate controls."""

    def test_exact_duplicate(self, matcher):
        p1 = make_payment(amount=10000.0)
        p1.signals = PaymentSignals(fingerprint="abc123")
        p2 = make_payment(amount=10000.0)
        p2.id = "PAY-002"
        p2.signals = PaymentSignals(fingerprint="abc123")
        alerts = matcher.check_duplicates(p2, [p1])
        assert len(alerts) == 1
        assert alerts[0].alert_type == "EXACT_DUPLICATE"

    def test_same_day_same_amount(self, matcher):
        p1 = make_payment(amount=10000.0)
        p1.signals = PaymentSignals(fingerprint="abc")
        p2 = make_payment(amount=10000.0)
        p2.id = "PAY-002"
        p2.signals = PaymentSignals(fingerprint="def")
        alerts = matcher.check_duplicates(p2, [p1])
        assert any(a.alert_type == "SAME_DAY_SAME_AMOUNT" for a in alerts)


class TestInstallments:
    """C2.9 - Installment payment detection."""

    def test_30pct_installment(self, matcher):
        inv = make_invoice(amount=30000.0)
        payment = make_payment(amount=9000.0)
        payment.signals = PaymentSignals(keywords={"partial": True, "advance": True})
        result = matcher.match(payment, [inv])
        assert result is not None
        assert "INSTALLMENT_30PCT" in result.flags
