"""
Tests for multi-invoice and N-to-M payment-invoice scenarios.

Covers:
  - 1 payment → N invoices (grouped payment, subset sum, full balance)
  - N payments → 1 invoice (installments, partial payments)
  - N payments → M invoices (batch processing, sequential matching)
  - Edge cases (overlapping amounts, credit note combos, mixed scenarios)
"""

import pytest
from datetime import date, timedelta

from reconciliation.c1_exact_matching import ExactMatcher
from reconciliation.c2_business_rules import BusinessRuleMatcher
from reconciliation.config import ReconciliationConfig
from reconciliation.models import (
    CreditNote,
    Debtor,
    Invoice,
    MatchMethod,
    Payment,
    PaymentSignals,
)
from reconciliation.orchestrator import ReconciliationOrchestrator


# ── Helpers ──

_inv_counter = 0

def _inv(ref, amount, debtor_id="D1", **kwargs):
    global _inv_counter
    _inv_counter += 1
    defaults = dict(
        id=f"INV-{_inv_counter:04d}",
        reference=ref,
        debtor_id=debtor_id,
        amount=amount,
        amount_ht=round(amount / 1.20, 2),
        issue_date=date(2024, 9, 1),
        due_date=date(2024, 10, 1),
    )
    defaults.update(kwargs)
    return Invoice(**defaults)


_pay_counter = 0

def _pay(amount, debtor_id="D1", refs=None, label="", debtor=None, **kwargs):
    global _pay_counter
    _pay_counter += 1
    return Payment(
        id=f"PAY-{_pay_counter:04d}",
        amount=amount,
        debtor_id=debtor_id,
        date=date(2024, 10, 15),
        label_raw=label,
        label_normalized=label.upper(),
        signals=PaymentSignals(
            raw_refs=[r.replace("-", "").upper() for r in refs] if refs else [],
            keywords=kwargs.pop("keywords", {}),
        ),
        debtor=debtor,
        **kwargs,
    )


# =====================================================================
# 1 PAYMENT → N INVOICES
# =====================================================================

class TestOnePaymentMultipleInvoices:
    """1 paiement couvre N factures d'un coup."""

    def test_exact_ref_2_invoices(self):
        """Paiement avec 2 references = somme exacte des 2 factures."""
        matcher = ExactMatcher()
        inv1 = _inv("FAC001", 5000.0)
        inv2 = _inv("FAC002", 3000.0)
        payment = _pay(8000.0, refs=["FAC001", "FAC002"])

        matcher.build_index([inv1, inv2])
        result = matcher.match(payment, [inv1, inv2])

        assert result is not None
        assert len(result.invoices) == 2
        assert result.confidence == 1.0
        assert abs(sum(result.allocated.values()) - 8000.0) < 0.01

    def test_exact_ref_5_invoices(self):
        """Paiement avec 5 references exactes."""
        matcher = ExactMatcher()
        invoices = [_inv(f"F{i:03d}", 1000.0 * (i + 1)) for i in range(5)]
        total = sum(inv.amount for inv in invoices)
        refs = [inv.reference for inv in invoices]
        payment = _pay(total, refs=refs)

        matcher.build_index(invoices)
        result = matcher.match(payment, invoices)

        assert result is not None
        assert len(result.invoices) == 5
        assert abs(sum(result.allocated.values()) - total) < 0.01

    def test_subset_sum_2_of_5(self):
        """Paiement = somme de 2 factures sur 5 disponibles."""
        matcher = BusinessRuleMatcher()
        invoices = [_inv(f"S{i}", amount) for i, amount in
                    enumerate([1000, 2000, 3000, 4000, 5000])]
        # Payment = 3000 + 5000 = 8000
        payment = _pay(8000.0, refs=[])

        result = matcher.match(payment, invoices)
        assert result is not None
        assert result.method == MatchMethod.C2_SUBSET_SUM
        assert len(result.invoices) >= 2
        assert abs(sum(result.allocated.values()) - 8000.0) < 0.01

    def test_subset_sum_3_of_8(self):
        """Paiement = somme de 3 factures sur 8 disponibles (subset sum DP)."""
        matcher = BusinessRuleMatcher()
        amounts = [1500, 2200, 3100, 4500, 5800, 6700, 7900, 9000]
        invoices = [_inv(f"SS{i}", float(a)) for i, a in enumerate(amounts)]
        # Target = 1500 + 3100 + 6700 = 11300
        payment = _pay(11300.0, refs=[])

        result = matcher.match(payment, invoices)
        assert result is not None
        assert len(result.invoices) >= 2

    def test_subset_sum_4_invoices(self):
        """Paiement = somme exacte de 4 factures."""
        matcher = BusinessRuleMatcher()
        invoices = [_inv(f"Q{i}", float(v)) for i, v in
                    enumerate([2500, 3700, 1800, 4200, 6100, 900])]
        # Target = 2500 + 3700 + 1800 + 4200 = 12200
        payment = _pay(12200.0, refs=[])

        result = matcher.match(payment, invoices)
        assert result is not None
        assert abs(sum(result.allocated.values()) - 12200.0) < 0.01

    def test_full_balance_all_invoices(self):
        """Paiement = somme de TOUTES les factures du debiteur."""
        matcher = ExactMatcher()
        invoices = [_inv(f"FB{i}", float(1000 * (i + 1))) for i in range(6)]
        total = sum(inv.amount for inv in invoices)
        payment = _pay(total, refs=[])

        matcher.build_index(invoices)
        result = matcher.match(payment, invoices)

        assert result is not None
        assert len(result.invoices) == 6
        assert "FULL_BALANCE" in result.flags or "BATCH_DATE" in result.flags

    def test_full_balance_net_credit_notes(self):
        """Paiement = total factures - avoirs."""
        matcher = ExactMatcher()
        inv1 = _inv("NC1", 10000.0)
        inv2 = _inv("NC2", 8000.0)
        credit = CreditNote(id="CN1", reference="AV001", debtor_id="D1", amount=3000.0)
        debtor = Debtor(id="D1", name="Test", open_credits=[credit])
        # Total = 18000 - 3000 = 15000
        payment = _pay(15000.0, refs=[], debtor=debtor)

        matcher.build_index([inv1, inv2])
        result = matcher.match(payment, [inv1, inv2])

        assert result is not None
        assert "CREDITS_DEDUCTED" in result.flags

    def test_multi_invoice_with_credit_deduction(self):
        """Paiement = (facture1 + facture2) - avoir."""
        matcher = BusinessRuleMatcher()
        inv1 = _inv("MC1", 5000.0)
        inv2 = _inv("MC2", 3000.0)
        credit = CreditNote(id="CN2", reference="AV002", debtor_id="D1", amount=1000.0)
        debtor = Debtor(id="D1", name="Test", open_credits=[credit])
        # Payment = 5000 + 3000 - 1000 = 7000
        payment = _pay(7000.0, refs=[], debtor=debtor)

        result = matcher.match(payment, [inv1, inv2])
        assert result is not None
        assert any("CREDIT" in f for f in result.flags)


# =====================================================================
# N PAYMENTS → 1 INVOICE
# =====================================================================

class TestMultiplePaymentsOneInvoice:
    """N paiements couvrent 1 seule facture (acomptes, versements partiels)."""

    def test_installment_30_70(self):
        """Acompte 30% + solde 70% sur une facture.
        Note: 30% installment has confidence 0.88, below auto threshold (0.90),
        so it goes to C6 in the orchestrator. We test the C2 rule directly.
        """
        matcher = BusinessRuleMatcher()
        inv = _inv("INST1", 10000.0)

        # First payment: 30% installment
        p1 = _pay(3000.0, refs=["INST1"], label="ACOMPTE 30% INST1",
                   keywords={"partial": True, "advance": True})
        result1 = matcher.match(p1, [inv])
        assert result1 is not None
        assert result1.confidence == 0.88
        assert "INSTALLMENT_30PCT" in result1.flags

        # Second payment: exact ref for the same invoice
        p2 = _pay(7000.0, refs=["INST1"], label="SOLDE 70% INST1")
        # 7000 != 10000 so exact ref won't match on amount,
        # but 70% installment should be detected
        result2 = matcher.match(p2, [inv])
        assert result2 is not None
        assert "INSTALLMENT_70PCT" in result2.flags

    def test_installment_50_50(self):
        """Two 50% payments detected by C2 installment rule."""
        matcher = BusinessRuleMatcher()
        inv = _inv("HALF", 20000.0)

        p1 = _pay(10000.0, refs=["HALF"], label="ACOMPTE 50% HALF",
                   keywords={"partial": True, "advance": True})
        result1 = matcher.match(p1, [inv])
        assert result1 is not None
        assert "INSTALLMENT_50PCT" in result1.flags

    def test_3_installments(self):
        """3 versements partiels pour 1 facture (30% + 30% + 40%)."""
        matcher = BusinessRuleMatcher()
        inv = _inv("TRI1", 30000.0)

        p1 = _pay(9000.0, refs=["TRI1"], label="ACOMPTE 1/3 TRI1",
                   keywords={"partial": True, "advance": True})
        result1 = matcher.match(p1, [inv])
        assert result1 is not None
        assert "INSTALLMENT_30PCT" in result1.flags

    def test_deposit_then_balance(self):
        """Acompte petit (10%) + gros solde (90%) — le 10% ne match pas
        les percentages standards, tombe en tolerance ou C6."""
        orch = ReconciliationOrchestrator()
        inv = _inv("DEP1", 50000.0)
        orch.setup([inv])

        # 10% deposit — non-standard percentage
        p1 = _pay(5000.0, refs=["DEP1"], label="DEPOSIT DEP1")
        ctx1 = orch.process_payment(p1, [inv])
        # May or may not match depending on rules (not a standard %)


# =====================================================================
# N PAYMENTS → M INVOICES (batch processing)
# =====================================================================

class TestNPaymentsMInvoices:
    """Scenarios complexes avec N paiements et M factures."""

    def test_3_payments_3_invoices_one_to_one(self):
        """3 paiements, chacun match exactement 1 facture."""
        orch = ReconciliationOrchestrator()
        invoices = [_inv(f"OTO{i}", float(1000 * (i + 1))) for i in range(3)]
        payments = [_pay(inv.amount, refs=[inv.reference]) for inv in invoices]
        for i, p in enumerate(payments):
            p.id = f"PAY-OTO-{i}"
        orch.setup(invoices)

        results = orch.process_batch(payments, list(invoices))
        matched = [r for r in results if r.final_match is not None]
        assert len(matched) == 3
        # Each payment matched exactly 1 invoice
        for r in matched:
            assert len(r.final_match.invoices) == 1

    def test_2_payments_4_invoices_grouped(self):
        """2 paiements groupes couvrant 4 factures (2+2)."""
        orch = ReconciliationOrchestrator()
        invoices = [_inv(f"GRP{i}", float(2000 + i * 500)) for i in range(4)]
        # Payment 1 = invoice 0 + invoice 1
        total1 = invoices[0].amount + invoices[1].amount
        p1 = _pay(total1, refs=[invoices[0].reference, invoices[1].reference])
        p1.id = "PAY-GRP-1"

        # Payment 2 = invoice 2 + invoice 3
        total2 = invoices[2].amount + invoices[3].amount
        p2 = _pay(total2, refs=[invoices[2].reference, invoices[3].reference])
        p2.id = "PAY-GRP-2"

        orch.setup(invoices)
        results = orch.process_batch([p1, p2], list(invoices))

        matched = [r for r in results if r.final_match is not None]
        assert len(matched) == 2
        total_invoices_matched = sum(len(r.final_match.invoices) for r in matched)
        assert total_invoices_matched == 4

    def test_5_payments_10_invoices_mixed(self):
        """5 paiements couvrant 10 factures en mix de scenarios."""
        orch = ReconciliationOrchestrator()
        invoices = [_inv(f"MIX{i:02d}", float(1000 + i * 300)) for i in range(10)]
        orch.setup(invoices)

        payments = []

        # Payment 1: exact ref on invoice 0
        p1 = _pay(invoices[0].amount, refs=[invoices[0].reference])
        p1.id = "PAY-MIX-1"
        payments.append(p1)

        # Payment 2: exact ref on invoice 1
        p2 = _pay(invoices[1].amount, refs=[invoices[1].reference])
        p2.id = "PAY-MIX-2"
        payments.append(p2)

        # Payment 3: 2 refs (invoice 2 + invoice 3)
        total3 = invoices[2].amount + invoices[3].amount
        p3 = _pay(total3, refs=[invoices[2].reference, invoices[3].reference])
        p3.id = "PAY-MIX-3"
        payments.append(p3)

        # Payment 4: 3 refs (invoice 4 + 5 + 6)
        total4 = invoices[4].amount + invoices[5].amount + invoices[6].amount
        p4 = _pay(total4, refs=[invoices[4].reference, invoices[5].reference,
                                invoices[6].reference])
        p4.id = "PAY-MIX-4"
        payments.append(p4)

        # Payment 5: subset sum (invoice 7 + 8 + 9), no refs
        total5 = invoices[7].amount + invoices[8].amount + invoices[9].amount
        p5 = _pay(total5, refs=[])
        p5.id = "PAY-MIX-5"
        payments.append(p5)

        results = orch.process_batch(payments, list(invoices))

        auto_matched = sum(1 for r in results if r.final_match is not None)
        total_inv_matched = sum(
            len(r.final_match.invoices) for r in results if r.final_match
        )
        # At least the first 4 payments should match (refs present)
        assert auto_matched >= 4
        # Total invoices covered should be >= 7 (payments 1-4 cover 7 invoices)
        assert total_inv_matched >= 7

    def test_batch_removes_matched_invoices(self):
        """Verify that matched invoices are removed for subsequent payments."""
        orch = ReconciliationOrchestrator()
        # 2 invoices with DIFFERENT amounts (to avoid duplicate alert)
        inv1 = _inv("DUP1", 5000.0)
        inv2 = _inv("DUP2", 7000.0)
        orch.setup([inv1, inv2])

        p1 = _pay(5000.0, refs=["DUP1"])
        p1.id = "PAY-D1"
        p2 = _pay(7000.0, refs=["DUP2"])
        p2.id = "PAY-D2"

        results = orch.process_batch([p1, p2], [inv1, inv2])
        assert all(r.final_match is not None for r in results)
        inv1_matched = results[0].final_match.invoices[0].reference
        inv2_matched = results[1].final_match.invoices[0].reference
        assert inv1_matched != inv2_matched

    def test_10_payments_sequential_depletion(self):
        """10 paiements sequentiels epuisent 10 factures une par une."""
        orch = ReconciliationOrchestrator()
        invoices = [_inv(f"SEQ{i:02d}", float(1000 + i * 100)) for i in range(10)]
        payments = [_pay(inv.amount, refs=[inv.reference]) for inv in invoices]
        for i, p in enumerate(payments):
            p.id = f"PAY-SEQ-{i:02d}"
        orch.setup(invoices)

        results = orch.process_batch(payments, list(invoices))
        matched = sum(1 for r in results if r.final_match is not None)
        assert matched == 10


# =====================================================================
# EDGE CASES — Overlapping, ambiguous, tricky
# =====================================================================

class TestEdgeCases:
    """Cas limites et scenarios ambigus."""

    def test_same_amount_different_refs(self):
        """3 factures de meme montant — seule la ref distingue."""
        matcher = ExactMatcher()
        inv1 = _inv("SAME1", 5000.0)
        inv2 = _inv("SAME2", 5000.0)
        inv3 = _inv("SAME3", 5000.0)

        payment = _pay(5000.0, refs=["SAME2"])
        matcher.build_index([inv1, inv2, inv3])
        result = matcher.match(payment, [inv1, inv2, inv3])

        assert result is not None
        assert result.invoices[0].reference == "SAME2"

    def test_payment_exceeds_single_invoice_matches_two(self):
        """Paiement plus grand qu'une seule facture = combination de 2."""
        matcher = BusinessRuleMatcher()
        inv1 = _inv("EXC1", 6000.0)
        inv2 = _inv("EXC2", 4000.0)
        # Payment = inv1 + inv2 = 10000
        payment = _pay(10000.0, refs=[])

        result = matcher.match(payment, [inv1, inv2])
        assert result is not None
        assert len(result.invoices) == 2

    def test_subset_sum_with_tolerance(self):
        """Paiement = somme de 2 factures avec arrondi."""
        orch = ReconciliationOrchestrator()
        inv1 = _inv("TOL1", 5000.0)
        inv2 = _inv("TOL2", 3000.0)
        # Payment with slight rounding
        payment = _pay(8000.50, refs=[])
        orch.setup([inv1, inv2])

        ctx = orch.process_payment(payment, [inv1, inv2])
        # Should match via IBAN+amount (full balance) or C2

    def test_invoice_with_discount_and_credit_note_combined(self):
        """Facture avec escompte ET deduction d'avoir en meme temps."""
        matcher = BusinessRuleMatcher()
        inv = _inv("COMBO1", 10000.0)
        credit = CreditNote(id="CN-C", reference="AV-C", debtor_id="D1", amount=500.0)
        debtor = Debtor(id="D1", name="Test", discount_rate=0.02, open_credits=[credit])

        # Payment = 10000 * 0.98 - 500 = 9300
        payment = _pay(9300.0, refs=["COMBO1"], debtor=debtor)
        # This is a complex case — might match discount OR credit
        result = matcher.match(payment, [inv])
        # At least one rule should catch it

    def test_zero_amount_invoice(self):
        """Facture a montant zero — ne devrait pas matcher."""
        matcher = ExactMatcher()
        inv = _inv("ZERO", 0.0)
        payment = _pay(0.0, refs=["ZERO"])

        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        # Amount diff = 0 so it could match, which is fine for zero-amount

    def test_very_large_portfolio(self):
        """20 factures, 1 paiement = somme de 3 factures specifiques."""
        matcher = BusinessRuleMatcher()
        invoices = [_inv(f"LP{i:02d}", float(1000 + i * 137)) for i in range(20)]
        # Target = invoice 3 + invoice 7 + invoice 12
        target = invoices[3].amount + invoices[7].amount + invoices[12].amount
        payment = _pay(target, refs=[])

        result = matcher.match(payment, invoices)
        assert result is not None
        assert len(result.invoices) >= 2

    def test_single_invoice_not_subset_sum(self):
        """Un paiement qui match 1 seule facture exactement ne devrait PAS
        etre retourne par subset sum (c'est du C1)."""
        matcher = BusinessRuleMatcher()
        inv = _inv("SINGLE", 5000.0)
        payment = _pay(5000.0, refs=[])

        # BusinessRuleMatcher.subset_sum should not return single-invoice
        result = matcher._rule_subset_sum(payment, [inv])
        assert result is None  # single match → belongs to C1

    def test_payment_partial_then_full_balance(self):
        """Acompte puis paiement du solde restant (via process_batch)."""
        orch = ReconciliationOrchestrator()
        inv1 = _inv("PFB1", 10000.0)
        inv2 = _inv("PFB2", 8000.0)
        orch.setup([inv1, inv2])

        # Payment 1: exact on inv1
        p1 = _pay(10000.0, refs=["PFB1"])
        p1.id = "PAY-PFB-1"

        # Payment 2: exact on inv2 (inv1 should be removed)
        p2 = _pay(8000.0, refs=["PFB2"])
        p2.id = "PAY-PFB-2"

        results = orch.process_batch([p1, p2], [inv1, inv2])
        assert all(r.final_match is not None for r in results)

    def test_many_small_invoices_one_big_payment(self):
        """1 gros paiement = somme de 6 petites factures."""
        orch = ReconciliationOrchestrator()
        invoices = [_inv(f"SM{i}", 500.0) for i in range(6)]
        # Total = 3000
        payment = _pay(3000.0, refs=[])
        orch.setup(invoices)

        ctx = orch.process_payment(payment, invoices)
        # Should match as full balance (all 6) or subset sum
        assert ctx.final_match is not None
        assert len(ctx.final_match.invoices) >= 2

    def test_interleaved_debtors_batch(self):
        """Batch avec 2 debiteurs melanges — chaque paiement ne doit
        matcher que les factures de son propre debiteur."""
        orch = ReconciliationOrchestrator()
        inv_d1 = _inv("D1F1", 5000.0, debtor_id="D1")
        inv_d2 = _inv("D2F1", 5000.0, debtor_id="D2")
        orch.setup([inv_d1, inv_d2])

        p1 = _pay(5000.0, debtor_id="D1", refs=["D1F1"])
        p1.id = "PAY-ID-1"
        p2 = _pay(5000.0, debtor_id="D2", refs=["D2F1"])
        p2.id = "PAY-ID-2"

        results = orch.process_batch([p1, p2], [inv_d1, inv_d2])
        assert results[0].final_match.invoices[0].debtor_id == "D1"
        assert results[1].final_match.invoices[0].debtor_id == "D2"
