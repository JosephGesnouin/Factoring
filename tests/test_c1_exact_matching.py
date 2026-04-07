"""Tests for Layer C1 - Exact & Deterministic Matching."""

import pytest
from datetime import date

from reconciliation.c1_exact_matching import ExactMatcher, InvoiceHashIndex
from reconciliation.config import C1Config
from reconciliation.models import (
    CreditNote,
    Debtor,
    Invoice,
    ISO20022Fields,
    MatchMethod,
    Payment,
    PaymentSignals,
)


def make_invoice(ref="FAC-2024-001", amount=10000.0, debtor_id="D1", **kwargs):
    return Invoice(
        id=f"INV-{ref}",
        reference=ref,
        debtor_id=debtor_id,
        amount=amount,
        amount_ht=amount / 1.20,
        issue_date=date(2024, 9, 1),
        due_date=date(2024, 10, 1),
        **kwargs,
    )


def make_payment(amount=10000.0, debtor_id="D1", refs=None, label="", **kwargs):
    return Payment(
        id="PAY-001",
        amount=amount,
        debtor_id=debtor_id,
        date=date(2024, 10, 15),
        label_raw=label,
        label_normalized=label.upper(),
        signals=PaymentSignals(raw_refs=refs or []),
        **kwargs,
    )


@pytest.fixture
def matcher():
    return ExactMatcher()


class TestR001ExactRef:
    """R001 — Exact reference + exact amount."""

    def test_r001a_single_exact_match(self, matcher):
        inv = make_invoice("FAC2024001", 10000.0)
        payment = make_payment(10000.0, refs=["FAC2024001"])
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is not None
        assert result.confidence == 1.0
        assert result.method == MatchMethod.C1_EXACT_REF
        assert "R001-A" in result.rule_id

    def test_r001c_ht_amount_match(self, matcher):
        inv = make_invoice("FAC2024001", 12000.0)  # TTC
        inv.amount_ht = 10000.0
        payment = make_payment(10000.0, refs=["FAC2024001"])
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is not None
        assert result.confidence == 0.97
        assert "TVA_ISSUE" in result.flags

    def test_r001d_multi_ref_match(self, matcher):
        inv1 = make_invoice("FAC001", 5000.0)
        inv2 = make_invoice("FAC002", 3000.0)
        payment = make_payment(8000.0, refs=["FAC001", "FAC002"])
        matcher.build_index([inv1, inv2])
        result = matcher.match(payment, [inv1, inv2])
        assert result is not None
        assert result.confidence == 1.0
        assert len(result.invoices) == 2

    def test_no_match_wrong_amount(self, matcher):
        inv = make_invoice("FAC001", 10000.0)
        payment = make_payment(5000.0, refs=["FAC001"])
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is None

    def test_no_match_wrong_debtor(self, matcher):
        inv = make_invoice("FAC001", 10000.0, debtor_id="D2")
        payment = make_payment(10000.0, debtor_id="D1", refs=["FAC001"])
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is None


class TestR002ISO20022:
    """R002 — ISO 20022 structured reference."""

    def test_roc_ref_match(self, matcher):
        inv = make_invoice("FAC2024001", 10000.0)
        payment = make_payment(10000.0)
        payment.iso20022 = ISO20022Fields(roc_ref="FAC2024001")
        payment.signals.raw_refs = ["FAC2024001"]
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is not None
        assert result.method == MatchMethod.C1_ISO20022
        assert result.confidence == 1.0

    def test_end_to_end_id_match(self, matcher):
        inv = make_invoice("FAC2024001", 10000.0)
        payment = make_payment(10000.0)
        payment.iso20022 = ISO20022Fields(end_to_end_id="FAC2024001")
        payment.signals.raw_refs = ["FAC2024001"]
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is not None


class TestR004IBANAmount:
    """R004 — IBAN + exact amount."""

    def test_r004a_unique_amount(self, matcher):
        inv = make_invoice("FAC001", 10000.0)
        payment = make_payment(10000.0, refs=[])
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is not None
        assert result.rule_id == "R004-A"

    def test_r004b_full_balance(self, matcher):
        inv1 = make_invoice("FAC001", 5000.0)
        inv2 = make_invoice("FAC002", 3000.0)
        payment = make_payment(8000.0, refs=[])
        matcher.build_index([inv1, inv2])
        result = matcher.match(payment, [inv1, inv2])
        assert result is not None
        assert "FULL_BALANCE" in result.flags


class TestR005FullBalance:
    """R005 — Full debtor balance match."""

    def test_full_balance_with_credits(self, matcher):
        inv1 = make_invoice("FAC001", 5000.0)
        inv2 = make_invoice("FAC002", 3000.0)
        credit = CreditNote(id="CN1", reference="AV001", debtor_id="D1", amount=1000.0)
        debtor = Debtor(id="D1", name="Test", open_credits=[credit])

        payment = make_payment(7000.0, refs=[])  # 8000 - 1000 credit
        payment.debtor = debtor
        matcher.build_index([inv1, inv2])
        result = matcher.match(payment, [inv1, inv2])
        assert result is not None
        assert "CREDITS_DEDUCTED" in result.flags


class TestR006PO:
    """R006 — Purchase Order match."""

    def test_po_match(self, matcher):
        # Add two invoices with the same amount so R004-A (unique amount) doesn't fire
        inv = make_invoice("FAC001", 10000.0, po_number="PO12345")
        inv2 = make_invoice("FAC002", 10000.0)
        payment = make_payment(10000.0, refs=["PO12345"])
        matcher.build_index([inv, inv2])
        result = matcher.match(payment, [inv, inv2])
        assert result is not None
        assert result.method == MatchMethod.C1_PO_MATCH


class TestHashIndex:
    """Test the multi-format hash index."""

    def test_variant_lookup(self):
        index = InvoiceHashIndex()
        inv = make_invoice("FAC-2024-001234")
        index.index_invoice(inv)

        # Should find with various formats
        assert index.lookup("FAC2024001234") is not None
        assert index.lookup("FAC-2024-001234") is not None

    def test_missing_ref(self):
        index = InvoiceHashIndex()
        assert index.lookup("NONEXISTENT") is None
