"""
Layer C2 - Advanced Business Rules (Confidence 85-99%)
Encodes expert factoring knowledge: tolerances, temporal patterns,
multi-invoice matching, credit notes, installments, anti-duplicate controls.
100% deterministic and auditable - no AI.

Rules:
  C2.1 - Amount tolerance (R-M001 to R-M012)
  C2.2 - Temporal patterns
  C2.3 - Label pattern matching
  C2.4 - Subset sum (multi-invoice)
  C2.5 - Credit notes / avoirs
  C2.6 - Factoring-specific rules
  C2.7 - Group consolidation
  C2.8 - Anti-duplicate controls
  C2.9 - N-to-1 installment payments
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations
from typing import Any

from .config import C2Config
from .models import (
    CreditNote,
    Debtor,
    DuplicateAlert,
    Invoice,
    MatchMethod,
    MatchResult,
    Payment,
)

logger = logging.getLogger(__name__)


@dataclass
class ToleranceMatch:
    invoice: Invoice
    tolerance_type: str
    rule_id: str
    confidence: float
    expected_amount: float
    flags: list[str]


class BusinessRuleMatcher:
    """
    Layer C2: Advanced business rule matching.
    All rules are deterministic and produce auditable results.
    """

    def __init__(self, config: C2Config | None = None):
        self.config = config or C2Config()

    def match(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        """Run all C2 rules in priority order."""
        debtor_invoices = [
            inv for inv in open_invoices
            if not payment.debtor_id or inv.debtor_id == payment.debtor_id
        ]
        if not debtor_invoices:
            return None

        rules = [
            self._rule_tolerance_amount,
            self._rule_credit_note_deduction,
            self._rule_subset_sum,
            self._rule_installment,
            self._rule_temporal_pattern,
        ]

        for rule_fn in rules:
            result = rule_fn(payment, debtor_invoices)
            if result is not None:
                result.payment_id = payment.id
                result.layer = 2
                logger.info(
                    "C2 match: payment=%s method=%s rule=%s confidence=%.2f",
                    payment.id, result.method.value, result.rule_id, result.confidence,
                )
                return result

        return None

    def check_duplicates(self, payment: Payment, recent_payments: list[Payment]) -> list[DuplicateAlert]:
        """C2.8: Anti-duplicate controls."""
        alerts = []

        for other in recent_payments:
            if other.id == payment.id:
                continue

            # Exact duplicate (same fingerprint)
            if payment.signals.fingerprint == other.signals.fingerprint:
                alerts.append(DuplicateAlert(
                    payment_id=payment.id,
                    duplicate_of=other.id,
                    similarity_score=1.0,
                    alert_type="EXACT_DUPLICATE",
                ))
                continue

            # Same day, same amount, same debtor
            if (payment.date == other.date
                    and abs(payment.amount - other.amount) < 0.01
                    and payment.debtor_id == other.debtor_id):
                alerts.append(DuplicateAlert(
                    payment_id=payment.id,
                    duplicate_of=other.id,
                    similarity_score=0.90,
                    alert_type="SAME_DAY_SAME_AMOUNT",
                ))

            # Near duplicate (same amount ± rounding, same week)
            if (payment.date and other.date
                    and abs((payment.date - other.date).days) <= 3
                    and abs(payment.amount - other.amount) < 1.0
                    and payment.debtor_id == other.debtor_id):
                alerts.append(DuplicateAlert(
                    payment_id=payment.id,
                    duplicate_of=other.id,
                    similarity_score=0.85,
                    alert_type="NEAR_DUPLICATE",
                ))

        return alerts

    # -----------------------------------------------------------------------
    # C2.1 — Amount Tolerance Rules (R-M001 to R-M012)
    # -----------------------------------------------------------------------
    def _rule_tolerance_amount(
        self, payment: Payment, invoices: list[Invoice]
    ) -> MatchResult | None:
        amount = payment.amount
        debtor = payment.debtor

        for inv in invoices:
            result = self._check_all_tolerances(payment, inv, debtor)
            if result:
                return result

        return None

    def _check_all_tolerances(
        self, payment: Payment, inv: Invoice, debtor: Debtor | None
    ) -> MatchResult | None:
        amount = payment.amount
        diff = amount - inv.amount

        # R-M004: Rounding tolerance (±1€) — highest confidence tolerance
        if abs(diff) <= self.config.rounding_tolerance and abs(diff) > 0.009:
            return self._make_tolerance_result(
                payment, inv, "R-M004", 0.99, ["ROUNDING"]
            )

        # R-M001: International SWIFT fees
        if debtor and debtor.country and debtor.country not in _SEPA_COUNTRIES:
            if -self.config.swift_fee_max <= diff < 0:
                return self._make_tolerance_result(
                    payment, inv, "R-M001", 0.95, ["SWIFT_FEES"]
                )

        # R-M002: SEPA OUR fees
        bic_upper = (payment.bic_source or "").upper()
        label_upper = payment.label_normalized.upper()
        if "OUR" in bic_upper or "OUR" in label_upper:
            if -self.config.sepa_our_fee_max <= diff < 0:
                return self._make_tolerance_result(
                    payment, inv, "R-M002", 0.96, ["SEPA_OUR_FEES"]
                )

        # R-M003: Contractual discount
        if debtor and debtor.discount_rate > 0:
            expected = inv.amount * (1 - debtor.discount_rate)
            if abs(amount - expected) < inv.amount * 0.005:
                return self._make_tolerance_result(
                    payment, inv, "R-M003", 0.97, ["DISCOUNT_APPLIED"],
                    allocated_amount=expected,
                )

        # R-M005: Construction retention (retenue de garantie)
        if debtor and debtor.retention_rate > 0:
            expected = inv.amount * (1 - debtor.retention_rate)
            if abs(amount - expected) < inv.amount * 0.005:
                return self._make_tolerance_result(
                    payment, inv, "R-M005", 0.93, ["RETENTION_APPLIED"],
                    allocated_amount=expected,
                )
        if debtor and debtor.sector == "BTP":
            for rate in [0.03, 0.05, 0.10]:
                expected = inv.amount * (1 - rate)
                if abs(amount - expected) < inv.amount * 0.005:
                    return self._make_tolerance_result(
                        payment, inv, "R-M005", 0.91, ["RETENTION_BTP"],
                        allocated_amount=expected,
                    )

        # R-M009: RFA (year-end rebate)
        if debtor and debtor.rfa_rate > 0:
            expected = inv.amount * (1 - debtor.rfa_rate)
            if abs(amount - expected) < inv.amount * 0.005:
                return self._make_tolerance_result(
                    payment, inv, "R-M009", 0.91, ["RFA_DEDUCTED"],
                    allocated_amount=expected,
                )

        # R-M010: Withholding tax (international)
        if debtor and debtor.country in _WITHHOLDING_TAX_RATES:
            rate = _WITHHOLDING_TAX_RATES[debtor.country]
            expected = inv.amount * (1 - rate)
            if abs(amount - expected) < inv.amount * 0.01:
                return self._make_tolerance_result(
                    payment, inv, "R-M010", 0.90, ["WITHHOLDING_TAX"],
                    allocated_amount=expected,
                )

        # R-M012: Standard installment percentages
        for pct in self.config.standard_installment_pcts:
            expected = inv.amount * pct
            tolerance = inv.amount * self.config.installment_tolerance_pct
            if abs(amount - expected) < tolerance:
                return self._make_tolerance_result(
                    payment, inv, "R-M012", 0.88,
                    [f"INSTALLMENT_{int(pct * 100)}PCT"],
                    allocated_amount=expected,
                )

        return None

    # -----------------------------------------------------------------------
    # C2.5 — Credit Note / Avoir Deductions
    # -----------------------------------------------------------------------
    def _rule_credit_note_deduction(
        self, payment: Payment, invoices: list[Invoice]
    ) -> MatchResult | None:
        debtor = payment.debtor
        if not debtor or not debtor.open_credits:
            return None

        amount = payment.amount
        credits = debtor.open_credits

        for inv in invoices:
            # R-M007: Exact credit note deduction
            for cn in credits:
                expected = inv.amount - cn.amount
                if abs(amount - expected) < 0.01 and expected > 0:
                    return MatchResult(
                        payment_id=payment.id,
                        invoices=[inv],
                        method=MatchMethod.C2_CREDIT_NOTE,
                        confidence=0.97,
                        allocated={inv.reference: amount},
                        flags=["CREDIT_NOTE_DEDUCTED"],
                        credit_notes_applied=[cn],
                        rule_id="R-M007",
                    )

            # R-M006: Partial credit note
            for cn in credits:
                expected = inv.amount - cn.amount
                tolerance = inv.amount * 0.01
                if abs(amount - expected) < tolerance and expected > 0:
                    return MatchResult(
                        payment_id=payment.id,
                        invoices=[inv],
                        method=MatchMethod.C2_CREDIT_NOTE,
                        confidence=0.95,
                        allocated={inv.reference: amount},
                        flags=["PARTIAL_CREDIT_DEDUCTED"],
                        credit_notes_applied=[cn],
                        rule_id="R-M006",
                    )

        # Multi-invoice + credit note combination
        for n in range(2, min(len(invoices) + 1, 6)):
            for combo in combinations(invoices, n):
                combo_total = sum(inv.amount for inv in combo)
                for cn in credits:
                    expected = combo_total - cn.amount
                    if abs(amount - expected) < 0.01 and expected > 0:
                        return MatchResult(
                            payment_id=payment.id,
                            invoices=list(combo),
                            method=MatchMethod.C2_CREDIT_NOTE,
                            confidence=0.93,
                            allocated={inv.reference: inv.amount for inv in combo},
                            flags=["MULTI_INV_CREDIT_DEDUCTED"],
                            credit_notes_applied=[cn],
                            rule_id="R-M006-MULTI",
                        )

        return None

    # -----------------------------------------------------------------------
    # C2.4 — Subset Sum (Multi-Invoice Matching)
    # -----------------------------------------------------------------------
    def _rule_subset_sum(
        self, payment: Payment, invoices: list[Invoice]
    ) -> MatchResult | None:
        amount = payment.amount
        max_n = self.config.subset_sum_max_invoices

        # Sort by amount descending for better pruning
        sorted_invs = sorted(invoices, key=lambda i: i.amount, reverse=True)[:max_n]

        if len(sorted_invs) < 2:
            return None

        # Strategy 1: Greedy largest-first
        result = self._greedy_subset(amount, sorted_invs, payment)
        if result:
            return result

        # Strategy 2: Exact subset sum (DP for small N)
        if len(sorted_invs) <= 12:
            result = self._exact_subset_sum(amount, sorted_invs, payment)
            if result:
                return result

        # Strategy 3: Two-sum (pairs)
        result = self._two_sum_match(amount, sorted_invs, payment)
        if result:
            return result

        return None

    def _greedy_subset(
        self, target: float, invoices: list[Invoice], payment: Payment
    ) -> MatchResult | None:
        selected: list[Invoice] = []
        remaining = target

        for inv in invoices:
            if inv.amount <= remaining + 0.01:
                selected.append(inv)
                remaining -= inv.amount

            if abs(remaining) < 0.01:
                return MatchResult(
                    payment_id=payment.id,
                    invoices=selected,
                    method=MatchMethod.C2_SUBSET_SUM,
                    confidence=0.92,
                    allocated={inv.reference: inv.amount for inv in selected},
                    flags=["SUBSET_SUM_GREEDY"],
                    rule_id="R-SS-GREEDY",
                )

        return None

    def _exact_subset_sum(
        self, target: float, invoices: list[Invoice], payment: Payment
    ) -> MatchResult | None:
        """Brute-force subset sum for small N."""
        target_cents = round(target * 100)

        for n in range(2, min(len(invoices) + 1, 8)):
            for combo in combinations(invoices, n):
                combo_cents = sum(round(inv.amount * 100) for inv in combo)
                if abs(combo_cents - target_cents) <= 1:  # ±0.01€
                    return MatchResult(
                        payment_id=payment.id,
                        invoices=list(combo),
                        method=MatchMethod.C2_SUBSET_SUM,
                        confidence=0.94,
                        allocated={inv.reference: inv.amount for inv in combo},
                        flags=["SUBSET_SUM_EXACT"],
                        rule_id="R-SS-EXACT",
                    )

        return None

    def _two_sum_match(
        self, target: float, invoices: list[Invoice], payment: Payment
    ) -> MatchResult | None:
        """Optimized two-invoice sum check."""
        amounts: dict[int, Invoice] = {}
        target_cents = round(target * 100)

        for inv in invoices:
            inv_cents = round(inv.amount * 100)
            complement = target_cents - inv_cents
            if complement in amounts and amounts[complement].id != inv.id:
                other = amounts[complement]
                return MatchResult(
                    payment_id=payment.id,
                    invoices=[other, inv],
                    method=MatchMethod.C2_SUBSET_SUM,
                    confidence=0.95,
                    allocated={other.reference: other.amount, inv.reference: inv.amount},
                    flags=["TWO_SUM"],
                    rule_id="R-SS-TWO",
                )
            amounts[inv_cents] = inv

        return None

    # -----------------------------------------------------------------------
    # C2.9 — Installment / N-to-1 Payments
    # -----------------------------------------------------------------------
    def _rule_installment(
        self, payment: Payment, invoices: list[Invoice]
    ) -> MatchResult | None:
        """Detect installment patterns (multiple payments → 1 invoice)."""
        if not payment.signals.keywords.get("partial") and not payment.signals.keywords.get("advance"):
            return None

        amount = payment.amount
        for inv in invoices:
            if amount < inv.amount:
                ratio = amount / inv.amount
                for pct in self.config.standard_installment_pcts:
                    if abs(ratio - pct) < self.config.installment_tolerance_pct:
                        return MatchResult(
                            payment_id=payment.id,
                            invoices=[inv],
                            method=MatchMethod.C2_INSTALLMENT,
                            confidence=0.88,
                            allocated={inv.reference: amount},
                            flags=[f"INSTALLMENT_{int(pct * 100)}PCT", "PARTIAL_PAYMENT"],
                            rule_id="R-INST",
                        )
        return None

    # -----------------------------------------------------------------------
    # C2.2 — Temporal Pattern Rules
    # -----------------------------------------------------------------------
    def _rule_temporal_pattern(
        self, payment: Payment, invoices: list[Invoice]
    ) -> MatchResult | None:
        """Match based on temporal patterns and debtor payment habits."""
        if not payment.date:
            return None

        debtor = payment.debtor
        if not debtor:
            return None

        # Pattern: debtor pays exactly on due date + known delay
        avg_delay = debtor.avg_payment_delay
        if avg_delay > 0:
            for inv in invoices:
                if not inv.due_date:
                    continue
                expected_pay_date = inv.due_date + timedelta(days=int(avg_delay))
                date_diff = abs((payment.date - expected_pay_date).days)
                if date_diff <= 3 and abs(payment.amount - inv.amount) < 0.01:
                    return MatchResult(
                        payment_id=payment.id,
                        invoices=[inv],
                        method=MatchMethod.C2_TEMPORAL,
                        confidence=0.91,
                        allocated={inv.reference: inv.amount},
                        flags=["TEMPORAL_PATTERN_MATCH"],
                        rule_id="R-TEMP",
                    )

        # Pattern: period mentioned in label matches invoice dates
        periods = payment.signals.label_periods
        if periods:
            period_invoices = self._match_invoices_to_periods(periods, invoices, payment.date)
            if period_invoices:
                total = sum(inv.amount for inv in period_invoices)
                if abs(payment.amount - total) < 0.01:
                    return MatchResult(
                        payment_id=payment.id,
                        invoices=period_invoices,
                        method=MatchMethod.C2_TEMPORAL,
                        confidence=0.90,
                        allocated={inv.reference: inv.amount for inv in period_invoices},
                        flags=["PERIOD_MATCH"],
                        rule_id="R-TEMP-PERIOD",
                    )

        return None

    def _match_invoices_to_periods(
        self, periods: list[str], invoices: list[Invoice], pay_date: date
    ) -> list[Invoice]:
        """Find invoices matching mentioned periods."""
        MONTH_MAP = {
            "JANV": 1, "JANVIER": 1, "JAN": 1, "JANUARY": 1,
            "FEV": 2, "FEVRIER": 2, "FEB": 2, "FEBRUARY": 2,
            "MARS": 3, "MAR": 3, "MARCH": 3,
            "AVR": 4, "AVRIL": 4, "APR": 4, "APRIL": 4,
            "MAI": 5, "MAY": 5,
            "JUIN": 6, "JUN": 6, "JUNE": 6,
            "JUIL": 7, "JUILLET": 7, "JUL": 7, "JULY": 7,
            "AOUT": 8, "AUG": 8, "AUGUST": 8,
            "SEPT": 9, "SEPTEMBRE": 9, "SEP": 9, "SEPTEMBER": 9,
            "OCT": 10, "OCTOBRE": 10, "OCTOBER": 10,
            "NOV": 11, "NOVEMBRE": 11, "NOVEMBER": 11,
            "DEC": 12, "DECEMBRE": 12, "DECEMBER": 12,
        }

        target_months: set[tuple[int, int]] = set()  # (year, month)

        for period in periods:
            tokens = period.upper().split()
            month = None
            year = pay_date.year

            for token in tokens:
                if token in MONTH_MAP:
                    month = MONTH_MAP[token]
                elif token.isdigit():
                    y = int(token)
                    if y > 100:
                        year = y
                    elif y < 50:
                        year = 2000 + y
                    else:
                        year = 1900 + y

            if month:
                target_months.add((year, month))

        if not target_months:
            return []

        matched = [
            inv for inv in invoices
            if inv.issue_date and (inv.issue_date.year, inv.issue_date.month) in target_months
        ]
        return matched

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _make_tolerance_result(
        self,
        payment: Payment,
        inv: Invoice,
        rule_id: str,
        confidence: float,
        flags: list[str],
        allocated_amount: float | None = None,
    ) -> MatchResult:
        return MatchResult(
            payment_id=payment.id,
            invoices=[inv],
            method=MatchMethod.C2_TOLERANCE,
            confidence=confidence,
            allocated={inv.reference: allocated_amount or payment.amount},
            flags=flags,
            rule_id=rule_id,
        )


# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------
_SEPA_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU",
    "LV", "MC", "MT", "NL", "NO", "PL", "PT", "RO", "SE", "SI",
    "SK", "SM", "CH", "GB",
}

_WITHHOLDING_TAX_RATES = {
    "MA": 0.20,   # Morocco
    "DZ": 0.24,   # Algeria
    "TN": 0.15,   # Tunisia
    "TR": 0.18,   # Turkey
    "IN": 0.10,   # India
    "BR": 0.15,   # Brazil
    "AR": 0.21,   # Argentina
    "EG": 0.20,   # Egypt
}
