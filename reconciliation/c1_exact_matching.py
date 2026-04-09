"""
Layer C1 - Exact & Deterministic Matching (Confidence 97-100%)
Every rule here must have ~100% precision - zero false positives.
Execution target: <10ms per payment.

Rules:
  R001 - Exact reference + exact amount (A/B/C/D variants)
  R002 - ISO 20022 structured reference (6 SEPA fields)
  R003 - Hash index multi-format lookup
  R004 - IBAN + exact amount (A-E variants)
  R005 - Full debtor balance match
  R006 - Purchase Order (PO) match
  R007 - Bill of Lading (BL/CMR/DAE) match
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from .config import C1Config
from .models import (
    CreditNote,
    Debtor,
    Invoice,
    MatchMethod,
    MatchResult,
    Payment,
)
from .utils import normalize_ref

logger = logging.getLogger(__name__)


class InvoiceHashIndex:
    """
    Multi-format hash index for O(1) invoice lookup.
    Indexes every known variant of each invoice reference.

    Deterministic: uses the invoice's own ``issue_date.year`` for year
    variants rather than ``datetime.now()``, so indexing is reproducible
    regardless of when it runs.

    Stores multiple invoice IDs per variant (collisions allowed). Callers
    must disambiguate by amount/debtor when multiple matches are returned.
    """

    PREFIXES = [
        "FAC", "F", "FACT", "INV", "FC", "INVOICE", "BILL", "BL", "CMD", "BON",
    ]

    def __init__(self):
        # Store normalized variant → list of invoice_ids (not hash → single id).
        # Raw string keys are fine — MD5 was pure overhead.
        self._index: dict[str, list[str]] = {}

    def index_invoice(self, invoice: Invoice) -> None:
        ref = invoice.reference
        year = invoice.issue_date.year if invoice.issue_date else None
        for variant in self._generate_ref_variants(ref, year):
            self._index.setdefault(variant, []).append(invoice.id)

    def lookup(self, extracted_ref: str) -> str | None:
        """Return first invoice id matching the reference, or None.

        For disambiguation, use :meth:`lookup_all`.
        """
        ids = self.lookup_all(extracted_ref)
        return ids[0] if ids else None

    def lookup_all(self, extracted_ref: str) -> list[str]:
        """Return all candidate invoice ids matching the reference."""
        normalized = normalize_ref(extracted_ref)
        return self._index.get(normalized, [])

    def _normalize_ref(self, ref: str) -> str:
        return normalize_ref(ref)

    def _generate_ref_variants(self, ref: str, year: int | None = None) -> list[str]:
        variants: set[str] = set()
        norm = normalize_ref(ref)
        variants.add(norm)

        # With common prefixes
        num_part = re.sub(r"^[A-Z]+", "", norm)
        if num_part:
            for prefix in self.PREFIXES:
                variants.add(f"{prefix}{num_part}")

            # With/without leading zeros (padding 4-8)
            stripped = num_part.lstrip("0")
            if stripped:
                for pad in range(4, 9):
                    variants.add(stripped.zfill(pad))
                    for prefix in self.PREFIXES[:5]:
                        variants.add(f"{prefix}{stripped.zfill(pad)}")

        # With year variants (deterministic: uses invoice's own issue year)
        if year and num_part:
            for y in (str(year), str(year - 1), str(year)[2:]):
                variants.add(f"{y}{num_part}")
                variants.add(f"{num_part}{y}")

        return list(variants)


class ExactMatcher:
    """
    Layer C1: Deterministic matching rules.
    All rules return MatchResult only when certainty is very high.
    """

    def __init__(self, config: C1Config | None = None):
        self.config = config or C1Config()
        self._hash_index = InvoiceHashIndex()
        self._invoice_by_ref: dict[str, Invoice] = {}
        self._invoice_by_id: dict[str, Invoice] = {}
        self._po_invoice_map: dict[str, list[str]] = {}   # po_number → [invoice_id]
        self._bl_invoice_map: dict[str, list[str]] = {}   # bl_number → [invoice_id]

    def build_index(self, invoices: list[Invoice]) -> None:
        """Build all lookup indexes for the open invoice portfolio."""
        self._invoice_by_ref.clear()
        self._invoice_by_id.clear()
        self._po_invoice_map.clear()
        self._bl_invoice_map.clear()

        for inv in invoices:
            self._invoice_by_id[inv.id] = inv
            ref_key = normalize_ref(inv.reference)
            self._invoice_by_ref[ref_key] = inv
            self._hash_index.index_invoice(inv)

            if inv.po_number:
                po_key = normalize_ref(inv.po_number)
                self._po_invoice_map.setdefault(po_key, []).append(inv.id)

            if inv.bl_number:
                bl_key = normalize_ref(inv.bl_number)
                self._bl_invoice_map.setdefault(bl_key, []).append(inv.id)

    def match(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        """
        Run all C1 rules in priority order.
        Returns the first match found (highest confidence first).
        """
        # Ensure index is built
        if not self._invoice_by_id:
            self.build_index(open_invoices)

        # Rule priority order
        rules = [
            self._rule_r002_iso20022,
            self._rule_r001_exact_ref,
            self._rule_r003_hash_index,
            self._rule_r004_iban_amount,
            self._rule_r005_full_balance,
            self._rule_r006_po_match,
            self._rule_r007_bl_match,
        ]

        for rule_fn in rules:
            result = rule_fn(payment, open_invoices)
            if result is not None:
                result.payment_id = payment.id
                result.layer = 1
                logger.info(
                    "C1 match: payment=%s method=%s confidence=%.2f invoices=%d",
                    payment.id, result.method.value, result.confidence, len(result.invoices),
                )
                return result

        return None

    # -----------------------------------------------------------------------
    # R001 — Exact Reference + Exact Amount
    # -----------------------------------------------------------------------
    def _rule_r001_exact_ref(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        refs = payment.signals.raw_refs
        if not refs:
            return None

        matched_invoices: list[Invoice] = []
        total_matched = 0.0

        for ref in refs:
            ref_key = normalize_ref(ref)
            invoice = self._invoice_by_ref.get(ref_key)
            if invoice is None:
                continue
            if payment.debtor_id and invoice.debtor_id != payment.debtor_id:
                continue
            if not self._in_time_window(invoice, payment):
                # R001-B: Out of window but ref is certain
                matched_invoices.append(invoice)
                total_matched += invoice.amount
                continue
            matched_invoices.append(invoice)
            total_matched += invoice.amount

        if not matched_invoices:
            return None

        amount_diff = abs(payment.amount - total_matched)

        # R001-A / R001-D: Exact amount match
        if amount_diff < 0.01:
            return MatchResult(
                payment_id=payment.id,
                invoices=matched_invoices,
                method=MatchMethod.C1_EXACT_REF,
                confidence=1.0,
                allocated={inv.reference: inv.amount for inv in matched_invoices},
                flags=[],
                rule_id="R001-A" if len(matched_invoices) == 1 else "R001-D",
            )

        # R001-C: Amount matches HT total (VAT issue)
        ht_total = sum(inv.amount_ht for inv in matched_invoices)
        if ht_total > 0 and abs(payment.amount - ht_total) < 0.01:
            return MatchResult(
                payment_id=payment.id,
                invoices=matched_invoices,
                method=MatchMethod.C1_EXACT_REF_HT,
                confidence=0.97,
                allocated={inv.reference: inv.amount_ht for inv in matched_invoices},
                flags=["TVA_ISSUE"],
                rule_id="R001-C",
            )

        return None

    # -----------------------------------------------------------------------
    # R002 — ISO 20022 Structured Reference
    # -----------------------------------------------------------------------
    def _rule_r002_iso20022(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        iso = payment.iso20022

        # Priority order per spec: /ROC/ > /RFB/ > /INV/ > E2E > TxId > /BV/
        candidates = [
            (iso.roc_ref, 1.00, "ROC"),
            (iso.rfb_ref, 1.00, "RFB"),
            (iso.inv_number, 0.99, "INV"),
            (iso.end_to_end_id, 0.97, "E2E"),
            (iso.tx_id, 0.95, "TxId"),
            (iso.bv_ref, 0.93, "BV"),
        ]

        for ref_value, confidence, field_name in candidates:
            if not ref_value:
                continue

            ref_key = normalize_ref(ref_value)
            invoice = self._invoice_by_ref.get(ref_key)

            if invoice is None:
                # Try hash index for fuzzy format match
                inv_id = self._hash_index.lookup(ref_value)
                if inv_id:
                    invoice = self._invoice_by_id.get(inv_id)

            if invoice is None:
                continue

            # Verify debtor consistency
            if payment.debtor_id and invoice.debtor_id != payment.debtor_id:
                continue

            # Amount verification for highest confidence
            amount_ok = abs(payment.amount - invoice.amount) < 0.01

            return MatchResult(
                payment_id=payment.id,
                invoices=[invoice],
                method=MatchMethod.C1_ISO20022,
                confidence=confidence if amount_ok else confidence * 0.95,
                allocated={invoice.reference: min(payment.amount, invoice.amount)},
                flags=[] if amount_ok else ["AMOUNT_MISMATCH"],
                rule_id=f"R002-{field_name}",
            )

        return None

    # -----------------------------------------------------------------------
    # R003 — Hash Index Multi-Format
    # -----------------------------------------------------------------------
    def _rule_r003_hash_index(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        refs = payment.signals.raw_refs
        if not refs:
            return None

        for ref in refs:
            inv_id = self._hash_index.lookup(ref)
            if inv_id is None:
                continue

            invoice = self._invoice_by_id.get(inv_id)
            if invoice is None:
                continue

            if payment.debtor_id and invoice.debtor_id != payment.debtor_id:
                continue

            if abs(payment.amount - invoice.amount) < 0.01:
                return MatchResult(
                    payment_id=payment.id,
                    invoices=[invoice],
                    method=MatchMethod.C1_HASH_INDEX,
                    confidence=0.98,
                    allocated={invoice.reference: invoice.amount},
                    flags=[],
                    rule_id="R003",
                )

        return None

    # -----------------------------------------------------------------------
    # R004 — IBAN + Exact Amount
    # -----------------------------------------------------------------------
    def _rule_r004_iban_amount(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        if not payment.debtor_id:
            return None

        debtor_invoices = [
            inv for inv in open_invoices if inv.debtor_id == payment.debtor_id
        ]
        if not debtor_invoices:
            return None

        amount = payment.amount

        # R004-A: Single invoice with exact amount
        exact_matches = [inv for inv in debtor_invoices if abs(inv.amount - amount) < 0.01]
        if len(exact_matches) == 1:
            inv = exact_matches[0]
            if self._in_time_window(inv, payment, days=self.config.iban_unique_match_window_days):
                return MatchResult(
                    payment_id=payment.id,
                    invoices=[inv],
                    method=MatchMethod.C1_IBAN_AMOUNT,
                    confidence=0.98,
                    allocated={inv.reference: inv.amount},
                    flags=[],
                    rule_id="R004-A",
                )

        # R004-B: Amount = sum of ALL open invoices
        total_open = sum(inv.amount for inv in debtor_invoices)
        if abs(amount - total_open) < 0.01 and len(debtor_invoices) > 1:
            return MatchResult(
                payment_id=payment.id,
                invoices=debtor_invoices,
                method=MatchMethod.C1_IBAN_AMOUNT,
                confidence=0.96,
                allocated={inv.reference: inv.amount for inv in debtor_invoices},
                flags=["FULL_BALANCE"],
                rule_id="R004-B",
            )

        # R004-C: Amount = latest unpaid invoice of the month
        if payment.date:
            month_invoices = [
                inv for inv in debtor_invoices
                if inv.issue_date and inv.issue_date.month == payment.date.month
                and inv.issue_date.year == payment.date.year
            ]
            if len(month_invoices) == 1 and abs(month_invoices[0].amount - amount) < 0.01:
                inv = month_invoices[0]
                if inv.due_date and payment.date <= inv.due_date + timedelta(days=15):
                    return MatchResult(
                        payment_id=payment.id,
                        invoices=[inv],
                        method=MatchMethod.C1_IBAN_AMOUNT,
                        confidence=0.95,
                        allocated={inv.reference: inv.amount},
                        flags=["LATEST_INV"],
                        rule_id="R004-C",
                    )

        # R004-E: Amount = sum of invoices from a single batch date
        batch_groups: dict[date, list[Invoice]] = {}
        for inv in debtor_invoices:
            if inv.batch_date:
                batch_groups.setdefault(inv.batch_date, []).append(inv)
            elif inv.issue_date:
                batch_groups.setdefault(inv.issue_date, []).append(inv)

        for batch_date, batch_invs in batch_groups.items():
            batch_total = sum(inv.amount for inv in batch_invs)
            if abs(amount - batch_total) < 0.01 and len(batch_invs) > 1:
                return MatchResult(
                    payment_id=payment.id,
                    invoices=batch_invs,
                    method=MatchMethod.C1_IBAN_AMOUNT,
                    confidence=0.95,
                    allocated={inv.reference: inv.amount for inv in batch_invs},
                    flags=["BATCH_DATE"],
                    rule_id="R004-E",
                )

        return None

    # -----------------------------------------------------------------------
    # R005 — Full Balance Match
    # -----------------------------------------------------------------------
    def _rule_r005_full_balance(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        if not payment.debtor_id:
            return None

        debtor_invoices = [
            inv for inv in open_invoices if inv.debtor_id == payment.debtor_id
        ]
        if not debtor_invoices:
            return None

        total_open = sum(inv.amount for inv in debtor_invoices)

        if abs(payment.amount - total_open) < 0.01:
            return MatchResult(
                payment_id=payment.id,
                invoices=debtor_invoices,
                method=MatchMethod.C1_FULL_BALANCE,
                confidence=0.96,
                allocated={inv.reference: inv.amount for inv in debtor_invoices},
                flags=["FULL_BALANCE_CLEARED"],
                rule_id="R005",
            )

        # Net of credit notes
        debtor = payment.debtor
        if debtor and debtor.open_credits:
            credit_total = sum(c.amount for c in debtor.open_credits)
            net_balance = total_open - credit_total
            if abs(payment.amount - net_balance) < 0.01:
                return MatchResult(
                    payment_id=payment.id,
                    invoices=debtor_invoices,
                    method=MatchMethod.C1_FULL_BALANCE_NET_CREDITS,
                    confidence=0.95,
                    allocated={inv.reference: inv.amount for inv in debtor_invoices},
                    flags=["CREDITS_DEDUCTED"],
                    credit_notes_applied=list(debtor.open_credits),
                    rule_id="R005-NET",
                )

        return None

    # -----------------------------------------------------------------------
    # R006 — Purchase Order Match
    # -----------------------------------------------------------------------
    def _rule_r006_po_match(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        refs = payment.signals.raw_refs
        if not refs:
            return None

        for ref in refs:
            ref_key = normalize_ref(ref)
            invoice_ids = self._po_invoice_map.get(ref_key, [])
            if not invoice_ids:
                continue

            po_invoices = [self._invoice_by_id[iid] for iid in invoice_ids if iid in self._invoice_by_id]
            if not po_invoices:
                continue

            # Verify debtor
            if payment.debtor_id:
                po_invoices = [inv for inv in po_invoices if inv.debtor_id == payment.debtor_id]

            total = sum(inv.amount for inv in po_invoices)

            if abs(payment.amount - total) < 0.01:
                return MatchResult(
                    payment_id=payment.id,
                    invoices=po_invoices,
                    method=MatchMethod.C1_PO_MATCH,
                    confidence=0.96,
                    allocated={inv.reference: inv.amount for inv in po_invoices},
                    flags=[],
                    rule_id="R006",
                )

        return None

    # -----------------------------------------------------------------------
    # R007 — Bill of Lading / CMR / DAE Match
    # -----------------------------------------------------------------------
    def _rule_r007_bl_match(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        refs = payment.signals.raw_refs
        if not refs:
            return None

        for ref in refs:
            ref_key = normalize_ref(ref)
            invoice_ids = self._bl_invoice_map.get(ref_key, [])
            if not invoice_ids:
                continue

            bl_invoices = [self._invoice_by_id[iid] for iid in invoice_ids if iid in self._invoice_by_id]
            if not bl_invoices:
                continue

            if payment.debtor_id:
                bl_invoices = [inv for inv in bl_invoices if inv.debtor_id == payment.debtor_id]

            total = sum(inv.amount for inv in bl_invoices)

            if abs(payment.amount - total) < 0.01:
                return MatchResult(
                    payment_id=payment.id,
                    invoices=bl_invoices,
                    method=MatchMethod.C1_BL_MATCH,
                    confidence=0.95,
                    allocated={inv.reference: inv.amount for inv in bl_invoices},
                    flags=[],
                    rule_id="R007",
                )

        return None

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _in_time_window(self, invoice: Invoice, payment: Payment, days: int | None = None) -> bool:
        if not payment.date or not invoice.issue_date:
            return True  # Can't verify → assume within window
        window = days or self.config.time_window_days
        return (payment.date - invoice.issue_date).days <= window
