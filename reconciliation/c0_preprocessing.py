"""
Layer C0 - Preprocessing & Universal Normalization
Applied to 100% of incoming payments before any matching.
Must be idempotent, deterministic, and fully logged.
14 normalization transforms + contextual enrichment + signal extraction.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Any

from unidecode import unidecode

from .config import C0Config
from .models import (
    Currency,
    Debtor,
    ISO20022Fields,
    LabelClass,
    Payment,
    PaymentSignals,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference patterns (greedy extraction)
# ---------------------------------------------------------------------------
REF_PATTERNS = [
    # FAC-2024-001234, FACT/2024/001, F-001234
    re.compile(r"\b(FAC(?:T(?:URE)?)?[\s\-/]*\d{4}[\s\-/]*\d{3,10})\b", re.IGNORECASE),
    # INV-001234, INVOICE-001
    re.compile(r"\b(INV(?:OICE)?[\s\-/]*\d{3,10})\b", re.IGNORECASE),
    # FC-001234
    re.compile(r"\b(FC[\s\-/]*\d{3,10})\b", re.IGNORECASE),
    # Generic structured ref: 2-4 alpha + separator + digits
    re.compile(r"\b([A-Z]{2,4}[\-/]\d{4}[\-/]\d{3,8})\b"),
    # Pure numeric refs (6-10 digits, likely invoice numbers)
    re.compile(r"\b(\d{6,10})\b"),
    # BL refs
    re.compile(r"\b(BL[\s\-/]*\d{3,10})\b", re.IGNORECASE),
    # PO/CMD refs
    re.compile(r"\b((?:PO|CMD|BC)[\s\-/]*\d{3,10})\b", re.IGNORECASE),
    # CMR refs
    re.compile(r"\b(CMR[\s\-/]*\d{3,10})\b", re.IGNORECASE),
    # DAE refs
    re.compile(r"\b(DAE[\s\-/]*\d{4}[\s\-/]*\d{3,6})\b", re.IGNORECASE),
]

AMOUNT_PATTERN = re.compile(
    r"(\d{1,3}(?:[.\s]\d{3})*[,]\d{2}|\d{1,3}(?:[,\s]\d{3})*[.]\d{2}|\d+[.,]\d{2})"
)

DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    (re.compile(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b"), "%d/%m/%Y"),
    # DD/MM/YY
    (re.compile(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{2})\b"), "%d/%m/%y"),
    # YYYY-MM-DD (ISO)
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "%Y-%m-%d"),
]

PERIOD_PATTERNS = [
    re.compile(r"\b(JANV(?:IER)?|FEV(?:RIER)?|MARS|AVR(?:IL)?|MAI|JUIN|JUIL(?:LET)?|"
               r"AOUT|SEPT(?:EMBRE)?|OCT(?:OBRE)?|NOV(?:EMBRE)?|DEC(?:EMBRE)?)\s*(\d{2,4})?\b",
               re.IGNORECASE),
    re.compile(r"\b(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?|"
               r"JULY?|AUG(?:UST)?|SEPT?(?:EMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
               r"\s*(\d{2,4})?\b", re.IGNORECASE),
    re.compile(r"\b[QT]([1-4])\s*(\d{2,4})?\b", re.IGNORECASE),
    re.compile(r"\bS([12])\s*(\d{2,4})?\b", re.IGNORECASE),
]

KEYWORD_MAP = {
    "partial": ["ACOMPTE", "PARTIEL", "PARTIAL", "ADVANCE", "A VALOIR", "A COMPTE"],
    "credit_note": ["AVOIR", "CREDIT", "NOTE DE CREDIT", "CREDIT NOTE", "CN", "AVVOIR"],
    "advance": ["ACOMPTE", "ADVANCE", "AVANCE", "PREPAYMENT"],
    "final": ["SOLDE", "FINAL", "DERNIER", "CLOTURE", "BALANCE"],
    "penalty": ["PENALITE", "PENALTY", "INTERET", "INTEREST", "RETARD"],
    "discount": ["ESCOMPTE", "DISCOUNT", "REMISE"],
    "retention": ["RETENUE", "RETENTION", "GARANTIE"],
}

CURRENCY_MAP = {
    "€": "EUR", "EUR": "EUR", "EURO": "EUR", "EUROS": "EUR",
    "$": "USD", "USD": "USD", "US$": "USD", "USD$": "USD",
    "£": "GBP", "GBP": "GBP",
    "CHF": "CHF",
}

IBAN_PATTERN = re.compile(r"\b([A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{0,4}\s?\d{0,2})\b")

LANGUAGE_INDICATORS = {
    "EN": ["PAYMENT", "INVOICE", "AMOUNT", "TRANSFER", "RECEIPT", "BALANCE"],
    "FR": ["REGLEMENT", "FACTURE", "MONTANT", "VIREMENT", "PAIEMENT", "AVOIR"],
    "DE": ["ZAHLUNG", "RECHNUNG", "BETRAG", "UBERWEISUNG"],
    "NL": ["BETALING", "FACTUUR", "BEDRAG", "OVERSCHRIJVING"],
    "ES": ["PAGO", "FACTURA", "IMPORTE", "TRANSFERENCIA"],
    "IT": ["PAGAMENTO", "FATTURA", "IMPORTO", "BONIFICO"],
}


class PaymentPreprocessor:
    """
    Layer C0: Normalizes and enriches incoming payments.
    All 14 transformations from the specification (N001-N014).
    """

    def __init__(self, config: C0Config | None = None):
        self.config = config or C0Config()

    def process(
        self,
        payment: Payment,
        debtor_lookup: dict[str, Debtor] | None = None,
        iban_debtor_map: dict[str, str] | None = None,
    ) -> Payment:
        """Apply all C0 transformations to a payment."""
        # N001-N014: Normalize label
        payment.label_normalized = self.normalize_label(payment.label_raw)

        # Parse ISO 20022 fields if present in metadata
        payment.iso20022 = self._parse_iso20022(payment.metadata)

        # C0.2: Contextual enrichment
        if iban_debtor_map and debtor_lookup:
            payment = self._enrich_debtor(payment, iban_debtor_map, debtor_lookup)

        # C0.3: Signal extraction
        payment.signals = self.extract_signals(payment)

        return payment

    def normalize_label(self, label: str) -> str:
        """Apply all 14 normalization transforms (N001-N014)."""
        if not label:
            return ""

        text = label

        # N001: Uppercase
        text = text.upper()

        # N002: Deaccentuation
        text = unidecode(text)

        # N011: Strip bank prefixes (before N003 to preserve structure).
        # Loop until stable: stripping one prefix can expose another
        # (e.g. "VIREMENT RECU DE SEPA CREDIT TRANSFER FAC-001").
        changed = True
        max_iter = 5
        while changed and max_iter > 0:
            changed = False
            max_iter -= 1
            for prefix in self.config.bank_prefixes_to_strip:
                up = prefix.upper()
                if text.startswith(up):
                    text = text[len(up):].strip()
                    changed = True
                    break

        # N003: Strip punctuation except digits/letters/spaces
        text = re.sub(r"[^A-Z0-9\s]", " ", text)

        # N004: Normalize separators to space
        text = re.sub(r"[\-/\\.,;:_|]+", " ", text)

        # N006: Remove duplicate spaces
        text = re.sub(r"\s{2,}", " ", text).strip()

        # N007: Expand known abbreviations
        tokens = text.split()
        expanded = []
        for token in tokens:
            expanded.append(self.config.abbreviation_map.get(token, token))
        text = " ".join(expanded)

        return text

    def normalize_amount(self, raw: str) -> float | None:
        """N005: Parse amount from various European/US formats."""
        if not raw:
            return None
        cleaned = raw.strip()
        # European format: 15.000,50 → 15000.50
        if re.match(r"^\d{1,3}(\.\d{3})+,\d{2}$", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        # US format: 15,000.50 → 15000.50
        elif re.match(r"^\d{1,3}(,\d{3})+\.\d{2}$", cleaned):
            cleaned = cleaned.replace(",", "")
        # Simple comma decimal: 15000,50 → 15000.50
        elif "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def normalize_iban(self, iban: str) -> str:
        """N008: Normalize IBAN format."""
        if not iban:
            return ""
        return re.sub(r"\s+", "", iban.upper())

    def normalize_date(self, raw: str) -> date | None:
        """N009: Parse date from various formats."""
        for pattern, fmt in DATE_PATTERNS:
            m = pattern.search(raw)
            if m:
                try:
                    if fmt == "%d/%m/%Y":
                        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                    elif fmt == "%d/%m/%y":
                        year = int(m.group(3))
                        year += 2000 if year < 50 else 1900
                        return date(year, int(m.group(2)), int(m.group(1)))
                    elif fmt == "%Y-%m-%d":
                        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
        return None

    def normalize_currency(self, raw: str) -> Currency:
        """N010: Normalize currency symbol/code."""
        cleaned = raw.strip().upper()
        code = CURRENCY_MAP.get(cleaned, cleaned)
        try:
            return Currency(code)
        except ValueError:
            return Currency.EUR

    def detect_language(self, text: str) -> str:
        """N012: Detect label language."""
        text_upper = text.upper()
        scores: dict[str, int] = {}
        for lang, keywords in LANGUAGE_INDICATORS.items():
            scores[lang] = sum(1 for kw in keywords if kw in text_upper)
        if not scores or max(scores.values()) == 0:
            return "FR"  # default
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def tokenize_ngrams(self, text: str, ns: tuple[int, ...] = (3, 4, 5)) -> list[str]:
        """N013: Character n-gram tokenization."""
        cleaned = re.sub(r"\s+", "", text)
        ngrams = []
        for n in ns:
            for i in range(len(cleaned) - n + 1):
                ngrams.append(cleaned[i:i + n])
        return ngrams

    def pad_numeric(self, ref: str) -> str:
        """N014: Zero-pad numeric portion of references."""
        pad_len = self.config.numeric_padding_length

        def _pad(m: re.Match) -> str:
            return m.group(0).zfill(pad_len)

        return re.sub(r"\d+", _pad, ref)

    def extract_signals(self, payment: Payment) -> PaymentSignals:
        """C0.3: Extract preliminary signals from payment."""
        label = payment.label_normalized
        signals = PaymentSignals()

        # Signal 1: Raw references
        signals.raw_refs = self._extract_refs(label)

        # Also check ISO 20022 fields for references
        iso = payment.iso20022
        for field_val in [iso.roc_ref, iso.rfb_ref, iso.inv_number, iso.end_to_end_id]:
            if field_val:
                normalized = re.sub(r"[^A-Z0-9]", "", field_val.upper())
                if normalized and normalized not in signals.raw_refs:
                    signals.raw_refs.insert(0, normalized)

        # Signal 2: Amounts mentioned in label
        signals.label_amounts = self._extract_amounts(label)

        # Signal 3: Temporal periods
        signals.label_periods = self._extract_periods(label)

        # Signal 4: Business keywords
        signals.keywords = self._extract_keywords(label)

        # Signal 5: Label classification
        signals.label_class = self._classify_label(label, signals)

        # Signal 6: Label quality score
        signals.label_quality = self._compute_label_quality(label, signals)

        # Signal 7: Fingerprint
        signals.fingerprint = payment.fingerprint

        return signals

    def _extract_refs(self, label: str) -> list[str]:
        """Extract all potential references from label."""
        refs = []
        for pattern in REF_PATTERNS:
            for m in pattern.finditer(label):
                ref = re.sub(r"[^A-Z0-9]", "", m.group(1).upper())
                if ref and ref not in refs and len(ref) >= 3:
                    refs.append(ref)
        return refs

    def _extract_amounts(self, label: str) -> list[float]:
        """Extract amounts mentioned in the label text."""
        amounts = []
        for m in AMOUNT_PATTERN.finditer(label):
            val = self.normalize_amount(m.group(1))
            if val is not None and val > 0:
                amounts.append(val)
        return amounts

    def _extract_periods(self, label: str) -> list[str]:
        """Extract temporal period references."""
        periods = []
        for pattern in PERIOD_PATTERNS:
            for m in pattern.finditer(label):
                periods.append(m.group(0).upper().strip())
        return periods

    def _extract_keywords(self, label: str) -> dict[str, bool]:
        """Extract business keyword signals."""
        result = {}
        label_upper = label.upper()
        for category, keywords in KEYWORD_MAP.items():
            result[category] = any(kw in label_upper for kw in keywords)
        return result

    def _classify_label(self, label: str, signals: PaymentSignals) -> LabelClass:
        """Classify the label into one of the standard categories."""
        if not label or len(label.strip()) < 3:
            return LabelClass.EMPTY

        has_refs = len(signals.raw_refs) > 0
        has_periods = len(signals.label_periods) > 0
        has_amounts = len(signals.label_amounts) > 0

        if has_refs and len(signals.raw_refs) == 1 and not has_periods:
            return LabelClass.SINGLE_REF
        if has_refs and len(signals.raw_refs) > 1:
            return LabelClass.MULTI_REF
        if has_periods and not has_refs:
            return LabelClass.PERIOD_ONLY
        if has_amounts and not has_refs and not has_periods:
            return LabelClass.AMOUNT_ONLY
        if has_refs and has_periods:
            return LabelClass.MIXED

        # Check if cryptic (short, no clear semantic content)
        tokens = label.split()
        if len(tokens) <= 2 and not has_refs:
            return LabelClass.CRYPTIC

        return LabelClass.MIXED

    def _compute_label_quality(self, label: str, signals: PaymentSignals) -> float:
        """Compute quality score from 0.0 (empty/useless) to 1.0 (rich)."""
        if not label:
            return 0.0

        score = 0.0

        # Length contribution (0-0.2)
        score += min(len(label) / 100, 0.2)

        # Reference presence (0-0.3)
        if signals.raw_refs:
            score += 0.2 + min(len(signals.raw_refs) * 0.05, 0.1)

        # Period presence (0-0.15)
        if signals.label_periods:
            score += 0.15

        # Amount presence (0-0.15)
        if signals.label_amounts:
            score += 0.15

        # Keywords (0-0.2)
        keyword_count = sum(1 for v in signals.keywords.values() if v)
        score += min(keyword_count * 0.05, 0.2)

        return min(score, 1.0)

    def _enrich_debtor(
        self,
        payment: Payment,
        iban_debtor_map: dict[str, str],
        debtor_lookup: dict[str, Debtor],
    ) -> Payment:
        """C0.2: Enrich payment with debtor context from IBAN."""
        iban = self.normalize_iban(payment.iban_source)
        debtor_id = iban_debtor_map.get(iban)
        if debtor_id:
            payment.debtor_id = debtor_id
            debtor = debtor_lookup.get(debtor_id)
            if debtor:
                payment.debtor = debtor
        return payment

    def _parse_iso20022(self, metadata: dict[str, Any]) -> ISO20022Fields:
        """Parse ISO 20022 structured fields from payment metadata."""
        fields = ISO20022Fields()
        if not metadata:
            return fields

        iso = metadata.get("iso20022", {})
        fields.roc_ref = iso.get("roc_ref") or iso.get("CdtrRefInf_Ref")
        fields.rfb_ref = iso.get("rfb_ref") or iso.get("EndToEndId")
        fields.inv_number = iso.get("inv_number") or iso.get("RfrdDocInf_Nb")
        fields.end_to_end_id = iso.get("end_to_end_id") or iso.get("E2EId")
        fields.tx_id = iso.get("tx_id") or iso.get("TxId")
        fields.bv_ref = iso.get("bv_ref")

        return fields
