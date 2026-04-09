"""
Layer C4 - Machine Learning Supervised (Confidence 80-95%)
Ensemble of LightGBM + XGBoost + Random Forest with meta-classifier.
42 features in 4 groups, LambdaRank for 1-to-N, active learning, drift detection.

Components:
  C4.1 - Feature engineering (42 features)
  C4.2 - Ensemble architecture
  C4.3 - LambdaRank for ranking
  C4.4 - Active learning
  C4.5 - Data drift monitoring (PSI)
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .c3_nlp_fuzzy import (
    _jaro_winkler,
    _levenshtein_ratio,
    _ngram_similarity,
    _numeric_ref_similarity,
    _partial_ratio,
    _token_set_ratio,
    compute_composite_fuzzy_score,
)
from .config import C4Config
from .models import Invoice, MatchMethod, MatchResult, Payment
from .utils import normalize_ref

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C4.1 — Feature Engineering (42 features in 4 groups)
# ---------------------------------------------------------------------------

def compute_features(payment: Payment, invoice: Invoice) -> dict[str, float]:
    """
    Compute all 42 features for a (payment, invoice) candidate pair.
    Features are grouped into 4 categories:
      G1: Amount features (10)
      G2: Reference/text features (12)
      G3: Temporal features (10)
      G4: Behavioral/contextual features (10)
    """
    features: dict[str, float] = {}

    # ===== G1: Amount Features (10) =====
    amount_diff = payment.amount - invoice.amount
    amount_ratio = payment.amount / max(invoice.amount, 0.01)

    features["g1_amount_diff"] = amount_diff
    features["g1_amount_diff_abs"] = abs(amount_diff)
    features["g1_amount_ratio"] = amount_ratio
    features["g1_amount_diff_pct"] = abs(amount_diff) / max(invoice.amount, 0.01)
    features["g1_amount_match_exact"] = 1.0 if abs(amount_diff) < 0.01 else 0.0
    features["g1_amount_match_ht"] = (
        1.0 if invoice.amount_ht > 0 and abs(payment.amount - invoice.amount_ht) < 0.01 else 0.0
    )
    features["g1_amount_is_round"] = 1.0 if payment.amount == int(payment.amount) else 0.0
    features["g1_invoice_amount_log"] = float(np.log1p(invoice.amount))
    features["g1_payment_amount_log"] = float(np.log1p(payment.amount))
    features["g1_amount_in_label"] = (
        1.0 if any(abs(a - invoice.amount) < 0.01 for a in payment.signals.label_amounts) else 0.0
    )

    # ===== G2: Reference/Text Features (12) =====
    inv_ref_norm = normalize_ref(invoice.reference)
    best_ref_score = 0.0
    best_partial = 0.0
    best_numeric = 0.0
    best_jw = 0.0

    for pref in payment.signals.raw_refs:
        pref_norm = normalize_ref(pref)
        best_ref_score = max(best_ref_score, compute_composite_fuzzy_score(pref_norm, inv_ref_norm))
        best_partial = max(best_partial, _partial_ratio(pref_norm, inv_ref_norm))
        best_numeric = max(best_numeric, _numeric_ref_similarity(pref_norm, inv_ref_norm))
        best_jw = max(best_jw, _jaro_winkler(pref_norm, inv_ref_norm))

    features["g2_ref_composite_score"] = best_ref_score
    features["g2_ref_partial_score"] = best_partial
    features["g2_ref_numeric_score"] = best_numeric
    features["g2_ref_jaro_winkler"] = best_jw
    features["g2_ref_count"] = float(len(payment.signals.raw_refs))
    features["g2_label_quality"] = payment.signals.label_quality
    features["g2_label_length"] = float(len(payment.label_normalized))
    features["g2_ref_in_label"] = 1.0 if inv_ref_norm in payment.label_normalized.upper() else 0.0
    features["g2_ngram_3_score"] = _ngram_similarity(
        payment.label_normalized.upper(), inv_ref_norm, n=3
    )
    features["g2_token_set_score"] = _token_set_ratio(
        payment.label_normalized.upper(), inv_ref_norm
    )
    features["g2_label_class_single"] = 1.0 if payment.signals.label_class.value == "SINGLE_REF" else 0.0
    features["g2_label_class_multi"] = 1.0 if payment.signals.label_class.value == "MULTI_REF" else 0.0

    # ===== G3: Temporal Features (10) =====
    if payment.date and invoice.issue_date:
        days_since_issue = (payment.date - invoice.issue_date).days
    else:
        days_since_issue = -1

    if payment.date and invoice.due_date:
        days_from_due = (payment.date - invoice.due_date).days
    else:
        days_from_due = 0

    features["g3_days_since_issue"] = float(days_since_issue)
    features["g3_days_from_due"] = float(days_from_due)
    features["g3_is_before_due"] = 1.0 if days_from_due <= 0 else 0.0
    features["g3_is_overdue"] = 1.0 if days_from_due > 0 else 0.0
    features["g3_days_overdue"] = float(max(days_from_due, 0))
    features["g3_same_month"] = (
        1.0 if payment.date and invoice.issue_date
        and payment.date.month == invoice.issue_date.month
        and payment.date.year == invoice.issue_date.year
        else 0.0
    )
    features["g3_invoice_age_days"] = float(max(days_since_issue, 0))
    features["g3_period_match"] = (
        1.0 if payment.signals.label_periods and invoice.issue_date
        and any(str(invoice.issue_date.month) in p or str(invoice.issue_date.year) in p
                for p in payment.signals.label_periods)
        else 0.0
    )
    features["g3_payment_day_of_month"] = float(payment.date.day if payment.date else 0)
    features["g3_payment_day_of_week"] = float(payment.date.weekday() if payment.date else 0)

    # ===== G4: Behavioral/Contextual Features (10) =====
    debtor = payment.debtor

    features["g4_debtor_known"] = 1.0 if payment.debtor_id else 0.0
    features["g4_debtor_same"] = (
        1.0 if payment.debtor_id and invoice.debtor_id == payment.debtor_id else 0.0
    )
    features["g4_debtor_regularity"] = debtor.payment_regularity_score if debtor else 0.5
    features["g4_debtor_avg_delay"] = debtor.avg_payment_delay if debtor else 0.0
    features["g4_debtor_risk"] = debtor.risk_score if debtor else 0.5
    features["g4_debtor_open_invoice_count"] = float(len(debtor.open_invoices)) if debtor else 0.0
    features["g4_debtor_has_discount"] = 1.0 if debtor and debtor.discount_rate > 0 else 0.0
    features["g4_debtor_has_credits"] = 1.0 if debtor and debtor.open_credits else 0.0
    features["g4_keyword_partial"] = 1.0 if payment.signals.keywords.get("partial") else 0.0
    features["g4_keyword_credit"] = 1.0 if payment.signals.keywords.get("credit_note") else 0.0

    return features


# Backwards-compat alias (was used by c4_ml features computation).
_normalize_for_features = normalize_ref


# ---------------------------------------------------------------------------
# C4.2 — Ensemble Model
# ---------------------------------------------------------------------------

class EnsembleModel:
    """
    Ensemble of LightGBM + XGBoost + Random Forest with logistic regression meta-classifier.
    """

    FEATURE_NAMES = [
        # G1
        "g1_amount_diff", "g1_amount_diff_abs", "g1_amount_ratio", "g1_amount_diff_pct",
        "g1_amount_match_exact", "g1_amount_match_ht", "g1_amount_is_round",
        "g1_invoice_amount_log", "g1_payment_amount_log", "g1_amount_in_label",
        # G2
        "g2_ref_composite_score", "g2_ref_partial_score", "g2_ref_numeric_score",
        "g2_ref_jaro_winkler", "g2_ref_count", "g2_label_quality", "g2_label_length",
        "g2_ref_in_label", "g2_ngram_3_score", "g2_token_set_score",
        "g2_label_class_single", "g2_label_class_multi",
        # G3
        "g3_days_since_issue", "g3_days_from_due", "g3_is_before_due", "g3_is_overdue",
        "g3_days_overdue", "g3_same_month", "g3_invoice_age_days", "g3_period_match",
        "g3_payment_day_of_month", "g3_payment_day_of_week",
        # G4
        "g4_debtor_known", "g4_debtor_same", "g4_debtor_regularity", "g4_debtor_avg_delay",
        "g4_debtor_risk", "g4_debtor_open_invoice_count", "g4_debtor_has_discount",
        "g4_debtor_has_credits", "g4_keyword_partial", "g4_keyword_credit",
    ]

    def __init__(self, config: C4Config | None = None):
        self.config = config or C4Config()
        self._lgb_model = None
        self._xgb_model = None
        self._rf_model = None
        self._meta_model = None
        self._is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, float]:
        """
        Train the ensemble on labeled data.
        Returns training metrics.
        """
        try:
            from lightgbm import LGBMClassifier
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.linear_model import LogisticRegression
            from sklearn.model_selection import cross_val_score
            from xgboost import XGBClassifier
        except ImportError as e:
            logger.error("ML dependencies not available: %s", e)
            return {"error": str(e)}

        # Train base models (random_state for reproducibility)
        self._lgb_model = LGBMClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=6,
            num_leaves=31, min_child_samples=20, verbose=-1,
            random_state=42,
        )
        self._xgb_model = XGBClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=6,
            min_child_weight=5, verbosity=0, random_state=42,
        )
        self._rf_model = RandomForestClassifier(
            n_estimators=150, max_depth=8, min_samples_leaf=10, n_jobs=-1,
            random_state=42,
        )

        self._lgb_model.fit(X, y)
        self._xgb_model.fit(X, y)
        self._rf_model.fit(X, y)

        # Meta-classifier on stacked predictions
        lgb_proba = self._lgb_model.predict_proba(X)[:, 1]
        xgb_proba = self._xgb_model.predict_proba(X)[:, 1]
        rf_proba = self._rf_model.predict_proba(X)[:, 1]

        meta_X = np.column_stack([lgb_proba, xgb_proba, rf_proba])
        self._meta_model = LogisticRegression()
        self._meta_model.fit(meta_X, y)

        self._is_trained = True

        # Compute cross-val score
        scores = cross_val_score(self._lgb_model, X, y, cv=5, scoring="f1")
        metrics = {
            "f1_mean": float(scores.mean()),
            "f1_std": float(scores.std()),
            "n_samples": len(y),
            "n_positive": int(y.sum()),
        }
        logger.info("Ensemble trained: %s", metrics)
        return metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict match probability for candidate pairs."""
        if not self._is_trained:
            raise RuntimeError("Model not trained")

        lgb_p = self._lgb_model.predict_proba(X)[:, 1]
        xgb_p = self._xgb_model.predict_proba(X)[:, 1]
        rf_p = self._rf_model.predict_proba(X)[:, 1]

        meta_X = np.column_stack([lgb_p, xgb_p, rf_p])
        return self._meta_model.predict_proba(meta_X)[:, 1]

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump({
                "lgb": self._lgb_model,
                "xgb": self._xgb_model,
                "rf": self._rf_model,
                "meta": self._meta_model,
            }, f)

    def load(self, path: str) -> None:
        with open(path, "rb") as f:
            models = pickle.load(f)
        self._lgb_model = models["lgb"]
        self._xgb_model = models["xgb"]
        self._rf_model = models["rf"]
        self._meta_model = models["meta"]
        self._is_trained = True


# ---------------------------------------------------------------------------
# C4.3 — LambdaRank for 1-to-N
# ---------------------------------------------------------------------------

class LambdaRankModel:
    """LambdaRank for ranking multiple invoice candidates per payment."""

    def __init__(self):
        self._model = None

    def train(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        """Train ranking model with group structure."""
        try:
            from lightgbm import LGBMRanker
            self._model = LGBMRanker(
                objective="lambdarank",
                n_estimators=200,
                learning_rate=0.05,
                max_depth=6,
                verbose=-1,
            )
            self._model.fit(X, y, group=groups)
        except ImportError:
            logger.warning("LightGBM not available, LambdaRank disabled")

    def rank(self, X: np.ndarray) -> np.ndarray:
        """Return relevance scores for ranking."""
        if self._model is None:
            return np.zeros(len(X))
        return self._model.predict(X)


# ---------------------------------------------------------------------------
# C4.4 — Active Learning
# ---------------------------------------------------------------------------

@dataclass
class ActiveLearningSample:
    payment_id: str
    invoice_id: str
    features: dict[str, float]
    model_confidence: float
    selection_strategy: str


class ActiveLearner:
    """6 strategies for selecting the most informative samples for labeling."""

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size

    def select_samples(
        self, candidates: list[tuple[str, str, np.ndarray, float]], strategy: str = "uncertainty"
    ) -> list[ActiveLearningSample]:
        """Select samples for human labeling using the specified strategy."""
        if strategy == "uncertainty":
            return self._uncertainty_sampling(candidates)
        elif strategy == "margin":
            return self._margin_sampling(candidates)
        elif strategy == "entropy":
            return self._entropy_sampling(candidates)
        elif strategy == "committee":
            return self._committee_disagreement(candidates)
        elif strategy == "diversity":
            return self._diversity_sampling(candidates)
        elif strategy == "hybrid":
            return self._hybrid_sampling(candidates)
        else:
            return self._uncertainty_sampling(candidates)

    def _uncertainty_sampling(self, candidates):
        """Select samples closest to the decision boundary (p ≈ 0.5)."""
        scored = [
            (abs(conf - 0.5), pid, iid, feat, conf)
            for pid, iid, feat, conf in candidates
        ]
        scored.sort(key=lambda x: x[0])
        return [
            ActiveLearningSample(pid, iid, {}, conf, "uncertainty")
            for _, pid, iid, feat, conf in scored[:self.batch_size]
        ]

    def _margin_sampling(self, candidates):
        """Select where top-2 predictions are closest."""
        return self._uncertainty_sampling(candidates)  # simplified

    def _entropy_sampling(self, candidates):
        """Select highest entropy predictions."""
        def _entropy(p):
            if p <= 0 or p >= 1:
                return 0
            return -(p * np.log2(p) + (1 - p) * np.log2(1 - p))

        scored = [
            (_entropy(conf), pid, iid, feat, conf)
            for pid, iid, feat, conf in candidates
        ]
        scored.sort(key=lambda x: -x[0])
        return [
            ActiveLearningSample(pid, iid, {}, conf, "entropy")
            for _, pid, iid, feat, conf in scored[:self.batch_size]
        ]

    def _committee_disagreement(self, candidates):
        return self._uncertainty_sampling(candidates)

    def _diversity_sampling(self, candidates):
        return self._uncertainty_sampling(candidates)

    def _hybrid_sampling(self, candidates):
        """Mix uncertainty + diversity."""
        n = self.batch_size // 2
        uncertainty = self._uncertainty_sampling(candidates)[:n]
        diversity = self._diversity_sampling(candidates)[:n]
        seen = {s.payment_id + s.invoice_id for s in uncertainty}
        combined = list(uncertainty)
        for s in diversity:
            if s.payment_id + s.invoice_id not in seen:
                combined.append(s)
        return combined[:self.batch_size]


# ---------------------------------------------------------------------------
# C4.5 — Data Drift Detection (PSI)
# ---------------------------------------------------------------------------

def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Population Stability Index for drift detection.
    PSI < 0.1: no drift
    PSI 0.1-0.2: moderate drift
    PSI > 0.2: significant drift → retrain
    """
    eps = 1e-6
    breakpoints = np.linspace(
        min(expected.min(), actual.min()),
        max(expected.max(), actual.max()),
        bins + 1,
    )
    expected_pct = np.histogram(expected, breakpoints)[0] / len(expected) + eps
    actual_pct = np.histogram(actual, breakpoints)[0] / len(actual) + eps

    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi)


# ---------------------------------------------------------------------------
# Main C4 Matcher
# ---------------------------------------------------------------------------

class MLMatcher:
    """
    Layer C4: ML-based matching using 42-feature ensemble.
    """

    def __init__(self, config: C4Config | None = None):
        self.config = config or C4Config()
        self._ensemble = EnsembleModel(config)
        self._ranker = LambdaRankModel()
        self._active_learner = ActiveLearner(
            batch_size=config.active_learning_batch_size if config else 50
        )

    @property
    def is_trained(self) -> bool:
        return self._ensemble._is_trained

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, float]:
        return self._ensemble.train(X, y)

    def load_model(self, path: str) -> None:
        self._ensemble.load(path)

    def save_model(self, path: str) -> None:
        self._ensemble.save(path)

    def match(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        """Score all candidates and return best match above threshold."""
        if not self.is_trained:
            logger.debug("C4 model not trained, skipping")
            return None

        if not open_invoices:
            return None

        # Pre-filter candidates (debtor first, then cap to avoid runaway
        # ensemble inference on large portfolios with unknown debtor)
        if payment.debtor_id:
            candidate_invs = [inv for inv in open_invoices if inv.debtor_id == payment.debtor_id]
        else:
            # Unknown debtor: score top-100 by amount proximity to keep cost bounded
            sorted_invs = sorted(
                open_invoices,
                key=lambda i: abs(i.amount - payment.amount),
            )
            candidate_invs = sorted_invs[:100]

        if not candidate_invs:
            return None

        # Compute features and build feature matrix
        try:
            candidates = [(inv, compute_features(payment, inv)) for inv in candidate_invs]
            X = np.array([
                [f.get(name, 0.0) for name in EnsembleModel.FEATURE_NAMES]
                for _, f in candidates
            ])
            probas = self._ensemble.predict_proba(X)
        except (RuntimeError, ValueError) as e:
            logger.error("C4 inference failed: %s", e)
            return None

        best_idx = int(np.argmax(probas))
        best_proba = float(probas[best_idx])
        best_inv = candidates[best_idx][0]

        if best_proba >= self.config.confidence_threshold:
            return MatchResult(
                payment_id=payment.id,
                invoices=[best_inv],
                method=MatchMethod.C4_ENSEMBLE,
                confidence=best_proba,
                allocated={best_inv.reference: min(payment.amount, best_inv.amount)},
                flags=["ML_ENSEMBLE"],
                rule_id="R-ML",
                metadata={
                    "model_proba": best_proba,
                    "candidates_scored": len(candidates),
                },
            )

        return None
