"""
Configuration for the reconciliation system.
All thresholds, tolerances, and tunable parameters.
"""

from dataclasses import dataclass, field


@dataclass
class C0Config:
    """Layer 0 - Preprocessing configuration."""
    abbreviation_map: dict[str, str] = field(default_factory=lambda: {
        "REGLT": "REGLEMENT",
        "RGLT": "REGLEMENT",
        "RGT": "REGLEMENT",
        "REGL": "REGLEMENT",
        "MT": "MONTANT",
        "MNT": "MONTANT",
        "VIR": "VIREMENT",
        "VIRT": "VIREMENT",
        "PAIE": "PAIEMENT",
        "PMT": "PAIEMENT",
        "PAYMT": "PAIEMENT",
        "FACT": "FACTURE",
        "FAC": "FACTURE",
        "FC": "FACTURE",
        "AVO": "AVOIR",
        "CMD": "COMMANDE",
        "BDC": "BON DE COMMANDE",
        "LIV": "LIVRAISON",
        "BL": "BON DE LIVRAISON",
        "ECH": "ECHEANCE",
        "TRIM": "TRIMESTRE",
        "SEM": "SEMESTRE",
        "REF": "REFERENCE",
    })
    bank_prefixes_to_strip: list[str] = field(default_factory=lambda: [
        "VIRT RECU DE",
        "VIREMENT RECU DE",
        "PAYMENT FROM",
        "PAIEMENT DE",
        "VIR DE",
        "VIR RECU",
        "CREDIT TRANSFER FROM",
        "SEPA CREDIT TRANSFER",
        "SCT",
        "REMISE",
        "ENCAISSEMENT",
    ])
    numeric_padding_length: int = 6


@dataclass
class C1Config:
    """Layer 1 - Exact matching configuration."""
    time_window_days: int = 180
    iban_unique_match_window_days: int = 120
    full_balance_min_invoices: int = 1
    po_partial_confidence: float = 0.88


@dataclass
class C2Config:
    """Layer 2 - Business rules configuration."""
    # Tolerance rules
    swift_fee_max: float = 35.0
    sepa_our_fee_max: float = 15.0
    rounding_tolerance: float = 1.0
    fx_tolerance_pct: float = 0.01  # 1%
    # Temporal
    late_payment_buffer_days: int = 15
    # Subset sum
    subset_sum_max_invoices: int = 15
    subset_sum_timeout_ms: int = 500
    # Installments
    standard_installment_pcts: list[float] = field(
        default_factory=lambda: [0.3, 0.4, 0.5, 0.7]
    )
    installment_tolerance_pct: float = 0.01


@dataclass
class C3Config:
    """Layer 3 - NLP/Fuzzy configuration."""
    fuzzy_min_score: float = 0.75
    tfidf_ngram_range: tuple[int, int] = (2, 4)
    ner_confidence_threshold: float = 0.70


@dataclass
class C4Config:
    """Layer 4 - ML configuration."""
    confidence_threshold: float = 0.85
    ensemble_weights: dict[str, float] = field(default_factory=lambda: {
        "lightgbm": 0.4,
        "xgboost": 0.35,
        "random_forest": 0.25,
    })
    active_learning_batch_size: int = 50
    drift_psi_threshold: float = 0.2
    retrain_interval_days: int = 7


@dataclass
class C5Config:
    """Layer 5 - LLM configuration."""
    # ── Provider & model ──
    provider: str = "anthropic"  # "anthropic" | "openai" | "disabled"
    model: str = "claude-sonnet-4-20250514"

    # ── API credentials (user-provided) ──
    # If None, falls back to env vars ANTHROPIC_API_KEY / OPENAI_API_KEY.
    # Set explicitly to inject your own key:
    #   cfg.c5.api_key = "sk-ant-..."
    #   cfg.c5.api_key = "sk-..."
    api_key: str | None = None
    base_url: str | None = None          # for custom endpoints / proxies / Azure
    organization: str | None = None      # OpenAI organization ID

    # ── Generation parameters ──
    max_tokens: int = 1024
    temperature: float = 0.0
    max_retries: int = 2
    timeout_seconds: float = 30.0

    # ── Cost control ──
    enabled: bool = True                 # global kill switch
    cost_limit_per_payment_usd: float = 0.05
    monthly_budget_usd: float = 500.0
    cache_ttl_hours: int = 24


@dataclass
class C6Config:
    """Layer 6 - Human review configuration."""
    queue_max_size: int = 1000
    priority_weights: dict[str, float] = field(default_factory=lambda: {
        "amount": 0.3,
        "age": 0.25,
        "confidence_gap": 0.25,
        "debtor_risk": 0.2,
    })
    sla_hours: int = 24


@dataclass
class OrchestratorConfig:
    """Global orchestrator configuration."""
    auto_match_confidence_threshold: float = 0.90
    escalation_confidence_threshold: float = 0.50
    layer_timeout_ms: dict[str, int] = field(default_factory=lambda: {
        "C0": 100,
        "C1": 50,
        "C2": 200,
        "C3": 500,
        "C4": 1000,
        "C5": 5000,
        "C6": 0,  # async
    })
    max_candidates_per_layer: int = 10
    enable_parallel_c2_c3: bool = True


@dataclass
class ReconciliationConfig:
    """Root configuration object."""
    c0: C0Config = field(default_factory=C0Config)
    c1: C1Config = field(default_factory=C1Config)
    c2: C2Config = field(default_factory=C2Config)
    c3: C3Config = field(default_factory=C3Config)
    c4: C4Config = field(default_factory=C4Config)
    c5: C5Config = field(default_factory=C5Config)
    c6: C6Config = field(default_factory=C6Config)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
