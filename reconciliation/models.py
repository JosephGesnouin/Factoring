"""
Core data models for the reconciliation system.
Defines Payment, Invoice, MatchResult, and all supporting types.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class MatchMethod(str, Enum):
    """Identifies which layer/rule produced the match."""
    # C1 - Exact
    C1_EXACT_REF = "C1_EXACT_REF"
    C1_EXACT_REF_HT = "C1_EXACT_REF_HT"
    C1_ISO20022 = "C1_ISO20022"
    C1_HASH_INDEX = "C1_HASH_INDEX"
    C1_IBAN_AMOUNT = "C1_IBAN_AMOUNT"
    C1_FULL_BALANCE = "C1_FULL_BALANCE"
    C1_FULL_BALANCE_NET_CREDITS = "C1_FULL_BALANCE_NET_CREDITS"
    C1_PO_MATCH = "C1_PO_MATCH"
    C1_BL_MATCH = "C1_BL_MATCH"
    # C2 - Business rules
    C2_TOLERANCE = "C2_TOLERANCE"
    C2_TEMPORAL = "C2_TEMPORAL"
    C2_LABEL_PATTERN = "C2_LABEL_PATTERN"
    C2_SUBSET_SUM = "C2_SUBSET_SUM"
    C2_CREDIT_NOTE = "C2_CREDIT_NOTE"
    C2_FACTORING = "C2_FACTORING"
    C2_GROUP = "C2_GROUP"
    C2_INSTALLMENT = "C2_INSTALLMENT"
    # C3 - NLP/Fuzzy
    C3_FUZZY = "C3_FUZZY"
    C3_NER = "C3_NER"
    C3_EMBEDDING = "C3_EMBEDDING"
    C3_NLP_COMBINED = "C3_NLP_COMBINED"
    C3_TFIDF = "C3_TFIDF"
    # C4 - ML
    C4_ENSEMBLE = "C4_ENSEMBLE"
    C4_LAMBDARANK = "C4_LAMBDARANK"
    # C5 - LLM
    C5_LLM = "C5_LLM"
    # C6 - Human
    C6_HUMAN = "C6_HUMAN"


class LabelClass(str, Enum):
    """Classification of payment label quality/type."""
    SINGLE_REF = "SINGLE_REF"
    MULTI_REF = "MULTI_REF"
    PERIOD_ONLY = "PERIOD_ONLY"
    AMOUNT_ONLY = "AMOUNT_ONLY"
    EMPTY = "EMPTY"
    CRYPTIC = "CRYPTIC"
    MIXED = "MIXED"


class Currency(str, Enum):
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    CHF = "CHF"


@dataclass
class Invoice:
    """Represents an open invoice in the factoring portfolio."""
    id: str
    reference: str
    debtor_id: str
    amount: float
    amount_ht: float
    currency: Currency = Currency.EUR
    issue_date: date | None = None
    due_date: date | None = None
    po_number: str | None = None
    bl_number: str | None = None
    status: str = "open"
    batch_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreditNote:
    """Represents a credit note / avoir."""
    id: str
    reference: str
    debtor_id: str
    amount: float
    issue_date: date | None = None
    expiry_date: date | None = None
    linked_invoice_ref: str | None = None
    consumed: bool = False


@dataclass
class Debtor:
    """Debtor profile with historical behavior data."""
    id: str
    name: str
    iban: str | None = None
    bic: str | None = None
    group_id: str | None = None
    country: str | None = None
    payment_terms: int = 30
    discount_rate: float = 0.0
    retention_rate: float = 0.0
    rfa_rate: float = 0.0
    avg_payment_delay: float = 0.0
    payment_regularity_score: float = 0.5
    known_payment_patterns: list[str] = field(default_factory=list)
    usual_invoice_counts_per_payment: int = 1
    risk_score: float = 0.5
    sector: str | None = None
    open_invoices: list[Invoice] = field(default_factory=list)
    open_credits: list[CreditNote] = field(default_factory=list)


@dataclass
class PaymentSignals:
    """Signals extracted from payment during C0 preprocessing."""
    raw_refs: list[str] = field(default_factory=list)
    label_amounts: list[float] = field(default_factory=list)
    label_periods: list[str] = field(default_factory=list)
    keywords: dict[str, bool] = field(default_factory=dict)
    label_class: LabelClass = LabelClass.EMPTY
    label_quality: float = 0.0
    fingerprint: str = ""


@dataclass
class ISO20022Fields:
    """Structured fields from SEPA/ISO 20022 payment messages."""
    roc_ref: str | None = None         # /ROC/ Creditor Reference
    rfb_ref: str | None = None         # /RFB/ Reference for Beneficiary
    inv_number: str | None = None      # /INV/ Invoice number
    end_to_end_id: str | None = None   # EndToEndId
    tx_id: str | None = None           # Transaction Identifier
    bv_ref: str | None = None          # Bill reference from unstructured


@dataclass
class Payment:
    """Represents an incoming payment to be reconciled."""
    id: str
    amount: float
    currency: Currency = Currency.EUR
    date: date | None = None
    label_raw: str = ""
    label_normalized: str = ""
    iban_source: str = ""
    bic_source: str = ""
    debtor_id: str | None = None
    debtor: Debtor | None = None
    signals: PaymentSignals = field(default_factory=PaymentSignals)
    iso20022: ISO20022Fields = field(default_factory=ISO20022Fields)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        raw = f"{self.iban_source}{self.amount}{self.date}{self.label_normalized}"
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Allocation:
    """Allocation of a payment amount to a specific invoice."""
    invoice_id: str
    invoice_ref: str
    allocated_amount: float


@dataclass
class MatchResult:
    """Result of a reconciliation attempt."""
    payment_id: str
    invoices: list[Invoice]
    method: MatchMethod
    confidence: float
    allocated: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    credit_notes_applied: list[CreditNote] = field(default_factory=list)
    explanation: str = ""
    layer: int = 0
    rule_id: str = ""
    processing_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_allocated(self) -> float:
        return sum(self.allocated.values())

    @property
    def is_auto(self) -> bool:
        return self.confidence >= 0.90


@dataclass
class ReconciliationContext:
    """Full context passed through the pipeline for a single payment."""
    payment: Payment
    open_invoices: list[Invoice]
    debtor: Debtor | None = None
    open_credits: list[CreditNote] = field(default_factory=list)
    candidate_matches: list[MatchResult] = field(default_factory=list)
    final_match: MatchResult | None = None
    layers_attempted: list[int] = field(default_factory=list)
    processing_log: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class DuplicateAlert:
    """Alert for potential duplicate payment."""
    payment_id: str
    duplicate_of: str
    similarity_score: float
    alert_type: str  # EXACT_DUPLICATE, NEAR_DUPLICATE, SAME_DAY_SAME_AMOUNT
