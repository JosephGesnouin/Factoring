"""
Reconciliation AI System - Payment-Invoice Matching for Factoring
6-Layer Architecture: C0 (Preprocessing) through C6 (Human Review)

Public API:
    from reconciliation import (
        ReconciliationOrchestrator, ReconciliationConfig,
        Payment, Invoice, Debtor, CreditNote, MatchResult,
    )
"""

__version__ = "1.1.0"

from .config import (
    C0Config,
    C1Config,
    C2Config,
    C3Config,
    C4Config,
    C5Config,
    C6Config,
    OrchestratorConfig,
    ReconciliationConfig,
)
from .models import (
    CreditNote,
    Currency,
    Debtor,
    DuplicateAlert,
    Invoice,
    ISO20022Fields,
    LabelClass,
    MatchMethod,
    MatchResult,
    Payment,
    PaymentSignals,
    ReconciliationContext,
)
from .orchestrator import PipelineMetrics, ReconciliationOrchestrator

__all__ = [
    "__version__",
    # Config
    "ReconciliationConfig",
    "C0Config", "C1Config", "C2Config", "C3Config",
    "C4Config", "C5Config", "C6Config", "OrchestratorConfig",
    # Models
    "Payment", "Invoice", "Debtor", "CreditNote", "MatchResult",
    "PaymentSignals", "ISO20022Fields", "MatchMethod", "LabelClass",
    "Currency", "DuplicateAlert", "ReconciliationContext",
    # Pipeline
    "ReconciliationOrchestrator", "PipelineMetrics",
]
