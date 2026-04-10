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
from datetime import date, timedelta
from itertools import combinations

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

    def check_duplicates(
        self,
        payment: Payment,
        recent_payments: "list[Payment] | DuplicateIndex",
    ) -> list[DuplicateAlert]:
        """C2.8: Anti-duplicate controls.

        Accepts either a list of recent payments (O(n) scan, legacy) or a
        ``DuplicateIndex`` for O(1) lookup at high volumes.
        Emits at most one alert per ``other`` payment to avoid double-counting.
        """
        alerts: list[DuplicateAlert] = []

        # Fast path: indexed lookup
        if isinstance(recent_payments, DuplicateIndex):
            dup_of = recent_payments.find_exact(payment)
            if dup_of and dup_of != payment.id:
                alerts.append(DuplicateAlert(
                    payment_id=payment.id, duplicate_of=dup_of,
                    similarity_score=1.0, alert_type="EXACT_DUPLICATE",
                ))
                return alerts
            dup_of = recent_payments.find_same_day_amount(payment)
            if dup_of and dup_of != payment.id:
                alerts.append(DuplicateAlert(
                    payment_id=payment.id, duplicate_of=dup_of,
                    similarity_score=0.90, alert_type="SAME_DAY_SAME_AMOUNT",
                ))
            return alerts

        # Legacy path: linear scan
        seen: set[str] = set()
        for other in recent_payments:
            if other.id == payment.id or other.id in seen:
                continue
            alert_type = None
            score = 0.0

            if payment.signals.fingerprint == other.signals.fingerprint:
                alert_type, score = "EXACT_DUPLICATE", 1.0
            elif (payment.date == other.date
                  and abs(payment.amount - other.amount) < 0.01
                  and payment.debtor_id == other.debtor_id):
                alert_type, score = "SAME_DAY_SAME_AMOUNT", 0.90
            elif (payment.date and other.date
                  and abs((payment.date - other.date).days) <= 3
                  and abs(payment.amount - other.amount) < 1.0
                  and payment.debtor_id == other.debtor_id):
                alert_type, score = "NEAR_DUPLICATE", 0.85

            if alert_type:
                alerts.append(DuplicateAlert(
                    payment_id=payment.id, duplicate_of=other.id,
                    similarity_score=score, alert_type=alert_type,
                ))
                seen.add(other.id)

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

        # Multi-invoice + credit note combination (limit to avoid combinatorial explosion)
        limited_invs = invoices[:10]
        for n in range(2, min(len(limited_invs) + 1, 5)):
            for combo in combinations(limited_invs, n):
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
        """Find a combination of invoices whose sum matches the payment.

        Tries multiple hypotheses in order of confidence:
          1. Exact sum (+-0.01 EUR)
          2. Sum with rounding (+-1 EUR)
          3. Sum minus SWIFT fees (up to -35 EUR for non-SEPA)
          4. Sum with escompte (sum x (1-discount%))
          5. Sum with retention (sum x (1-retention%))
          6. Sum with WHT (sum x (1-wht_rate))
          7. Sum minus credit note (sum - avoir)
        """
        amount = payment.amount
        max_n = self.config.subset_sum_max_invoices
        sorted_invs = sorted(invoices, key=lambda i: i.amount, reverse=True)[:max_n]

        if len(sorted_invs) < 2:
            return None

        debtor = payment.debtor

        # Build hypotheses: (target_sum, tol_cents, confidence, flags, rule_id)
        hypotheses = [
            (amount, 1, 0.94, ["SUBSET_SUM_EXACT"], "R-SS-EXACT"),
            (amount, 100, 0.92, ["SUBSET_SUM_ROUNDING"], "R-SS-ROUND"),
        ]

        # SWIFT fees: payment = sum - fee => sum = payment + fee
        if debtor and debtor.country and debtor.country not in _SEPA_COUNTRIES:
            for fee in [15, 20, 25, 30, 35]:
                hypotheses.append(
                    (amount + fee, 100, 0.90, ["SUBSET_SUM_SWIFT", f"FEE_{fee}EUR"], "R-SS-SWIFT"))

        # Escompte: payment = sum * (1-disc) => sum = payment / (1-disc)
        if debtor and debtor.discount_rate > 0:
            hypotheses.append(
                (amount / (1 - debtor.discount_rate), 100, 0.91,
                 ["SUBSET_SUM_DISCOUNT", f"ESC_{debtor.discount_rate*100:.0f}PCT"], "R-SS-DISC"))

        # Retention: payment = sum * (1-ret) => sum = payment / (1-ret)
        if debtor and debtor.retention_rate > 0:
            hypotheses.append(
                (amount / (1 - debtor.retention_rate), 100, 0.89,
                 ["SUBSET_SUM_RETENTION", f"RET_{debtor.retention_rate*100:.0f}PCT"], "R-SS-RET"))

        # WHT: payment = sum * (1-wht)
        if debtor and debtor.country in _WITHHOLDING_TAX_RATES:
            rate = _WITHHOLDING_TAX_RATES[debtor.country]
            hypotheses.append(
                (amount / (1 - rate), 100, 0.88,
                 ["SUBSET_SUM_WHT", f"WHT_{rate*100:.0f}PCT"], "R-SS-WHT"))

        # Credit note: payment = sum_inv - credit => sum_inv = payment + credit
        if debtor and debtor.open_credits:
            for cn in debtor.open_credits[:5]:
                hypotheses.append(
                    (amount + cn.amount, 100, 0.90,
                     ["SUBSET_SUM_CREDIT", f"DED_{cn.reference}"], "R-SS-CN"))

        for target, tol, conf, flags, rid in hypotheses:
            r = self._find_subset(target, tol, sorted_invs, payment, conf, flags, rid)
            if r:
                return r
        return None

    def _find_subset(self, target, tol_cents, invoices, payment, conf, flags, rid):
        """Try two-sum, greedy, then DP to find a subset summing to target."""
        r = self._two_sum_tol(target, tol_cents, invoices, payment, conf, flags, rid)
        if r: return r
        r = self._greedy_subset(target, invoices, payment, tol_cents, conf, flags, rid)
        if r: return r
        if len(invoices) <= 24:
            r = self._dp_subset(target, tol_cents, invoices, payment, conf, flags, rid)
            if r: return r
        return None

    def _greedy_subset(self, target, invoices, payment, tol_cents=1, conf=0.92, flags=None, rid="R-SS-GREEDY"):
        selected, remaining = [], target
        for inv in invoices:
            if inv.amount <= remaining + 0.01:
                selected.append(inv)
                remaining -= inv.amount
            if abs(remaining) * 100 <= tol_cents and len(selected) >= 2:
                return MatchResult(payment_id=payment.id, invoices=selected,
                    method=MatchMethod.C2_SUBSET_SUM, confidence=conf,
                    allocated={i.reference: i.amount for i in selected},
                    flags=list(flags or []), rule_id=rid)
        return None

    def _dp_subset(self, target, tol_cents, invoices, payment, conf=0.94, flags=None, rid="R-SS-DP"):
        """Meet-in-the-middle subset-sum with configurable tolerance."""
        import time as _t
        target_c = round(target * 100)
        n = len(invoices)
        if n < 2: return None
        deadline = _t.monotonic() + (self.config.subset_sum_timeout_ms / 1000.0)
        half = n // 2
        L, R = invoices[:half], invoices[half:]

        def _enum(items):
            sums = {0: ()}
            for i, inv in enumerate(items):
                if _t.monotonic() > deadline: break
                ic = round(inv.amount * 100)
                new = {}
                for s, idx in sums.items():
                    k = s + ic
                    if k not in sums and k not in new:
                        new[k] = idx + (i,)
                sums.update(new)
            return sums

        ls = _enum(L)
        if _t.monotonic() > deadline: return None
        rs = _enum(R)
        if _t.monotonic() > deadline: return None

        best = None
        for l_sum, l_idx in ls.items():
            if _t.monotonic() > deadline: break
            needed = target_c - l_sum
            for d in range(-tol_cents, tol_cents + 1):
                r_idx = rs.get(needed + d)
                if r_idx is None: continue
                if len(l_idx) + len(r_idx) < 2: continue
                combo = [L[i] for i in l_idx] + [R[i] for i in r_idx]
                if best is None or len(combo) < len(best):
                    best = combo

        if best:
            return MatchResult(payment_id=payment.id, invoices=best,
                method=MatchMethod.C2_SUBSET_SUM, confidence=conf,
                allocated={i.reference: i.amount for i in best},
                flags=list(flags or []), rule_id=rid)
        return None

    def _two_sum_tol(self, target, tol_cents, invoices, payment, conf=0.95, flags=None, rid="R-SS-TWO"):
        """Two-invoice sum with tolerance."""
        tc = round(target * 100)
        amounts = {}
        for inv in invoices:
            ic = round(inv.amount * 100)
            for d in range(-tol_cents, tol_cents + 1):
                comp = tc - ic + d
                if comp in amounts and amounts[comp].id != inv.id:
                    other = amounts[comp]
                    return MatchResult(payment_id=payment.id, invoices=[other, inv],
                        method=MatchMethod.C2_SUBSET_SUM, confidence=conf,
                        allocated={other.reference: other.amount, inv.reference: inv.amount},
                        flags=list(flags or []), rule_id=rid)
            amounts[ic] = inv
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


class DuplicateIndex:
    """O(1) indexed lookup for duplicate detection at scale.

    Maintains two indexes:
      * by fingerprint (SHA-256 of payment canonical form)
      * by (debtor_id, date, cents) composite key

    Usage:
        idx = DuplicateIndex()
        for payment in stream:
            alerts = matcher.check_duplicates(payment, idx)
            idx.add(payment)
    """

    def __init__(self, max_size: int = 100_000):
        self._by_fingerprint: dict[str, str] = {}
        self._by_key: dict[tuple, str] = {}
        self._insertion_order: list[str] = []
        self.max_size = max_size

    def _composite_key(self, payment: Payment) -> tuple:
        return (
            payment.debtor_id or "",
            payment.date,
            round(payment.amount * 100),  # cents to avoid float drift
        )

    def add(self, payment: Payment) -> None:
        fp = payment.signals.fingerprint
        if fp:
            self._by_fingerprint[fp] = payment.id
        self._by_key[self._composite_key(payment)] = payment.id
        self._insertion_order.append(payment.id)
        # FIFO eviction when exceeding max_size (best-effort — we don't
        # scan all entries to find the old fingerprint/key to stay O(1)).
        if len(self._insertion_order) > self.max_size:
            self._insertion_order.pop(0)

    def find_exact(self, payment: Payment) -> str | None:
        return self._by_fingerprint.get(payment.signals.fingerprint or "")

    def find_same_day_amount(self, payment: Payment) -> str | None:
        return self._by_key.get(self._composite_key(payment))

    def __len__(self) -> int:
        return len(self._insertion_order)


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
