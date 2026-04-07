"""
MLOps Pipeline - Continuous Improvement
Automated retraining, monitoring dashboard, drift detection,
and feedback loop integration.

Components:
  - Automatic retraining pipeline
  - 13 monitoring metrics dashboard
  - Data drift detection (PSI)
  - Feedback loop from C6 to C4
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .c4_ml import EnsembleModel, compute_features, compute_psi
from .c6_human_review import HumanReviewQueue, ReviewDecision
from .models import Invoice, MatchResult, Payment

logger = logging.getLogger(__name__)


@dataclass
class MonitoringMetrics:
    """13 key monitoring metrics for the reconciliation system."""
    # Volume metrics
    payments_per_hour: float = 0.0
    auto_match_rate: float = 0.0
    avg_processing_time_ms: float = 0.0

    # Quality metrics
    precision: float = 0.0          # TP / (TP + FP)
    recall: float = 0.0             # TP / (TP + FN)
    f1_score: float = 0.0
    false_positive_rate: float = 0.0

    # Layer distribution
    layer_distribution: dict[int, float] = field(default_factory=dict)

    # Business metrics
    sla_compliance_rate: float = 0.0
    human_review_backlog: int = 0
    avg_human_review_time_s: float = 0.0

    # Model health
    data_drift_psi: float = 0.0
    model_staleness_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "payments_per_hour": self.payments_per_hour,
            "auto_match_rate": f"{self.auto_match_rate:.1%}",
            "avg_processing_time_ms": f"{self.avg_processing_time_ms:.1f}",
            "precision": f"{self.precision:.3f}",
            "recall": f"{self.recall:.3f}",
            "f1_score": f"{self.f1_score:.3f}",
            "false_positive_rate": f"{self.false_positive_rate:.4f}",
            "layer_distribution": {
                f"C{k}": f"{v:.1%}" for k, v in self.layer_distribution.items()
            },
            "sla_compliance_rate": f"{self.sla_compliance_rate:.1%}",
            "human_review_backlog": self.human_review_backlog,
            "avg_human_review_time_s": f"{self.avg_human_review_time_s:.1f}",
            "data_drift_psi": f"{self.data_drift_psi:.4f}",
            "model_staleness_days": self.model_staleness_days,
        }


@dataclass
class TrainingRecord:
    """Record of a model training run."""
    timestamp: datetime
    n_samples: int
    n_positive: int
    metrics: dict[str, float]
    model_path: str
    trigger: str  # "scheduled", "drift", "feedback_threshold"


class MLOpsPipeline:
    """
    Continuous improvement pipeline.
    Manages retraining, monitoring, and feedback loops.
    """

    def __init__(
        self,
        model_dir: str = "./models",
        retrain_interval_days: int = 7,
        drift_threshold: float = 0.2,
        feedback_retrain_threshold: int = 100,
    ):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.retrain_interval_days = retrain_interval_days
        self.drift_threshold = drift_threshold
        self.feedback_retrain_threshold = feedback_retrain_threshold

        self._training_history: list[TrainingRecord] = []
        self._feature_distributions: dict[str, np.ndarray] = {}
        self._feedback_buffer: list[dict[str, Any]] = []
        self._predictions_log: list[dict[str, Any]] = []

    def collect_feedback(
        self,
        payment: Payment,
        predicted: MatchResult | None,
        actual_invoice_refs: list[str],
        actual_invoices: list[Invoice],
        decision: str,
    ) -> None:
        """Collect human feedback for model improvement."""
        record = {
            "payment_id": payment.id,
            "predicted_refs": [inv.reference for inv in predicted.invoices] if predicted else [],
            "predicted_confidence": predicted.confidence if predicted else 0.0,
            "actual_refs": actual_invoice_refs,
            "decision": decision,
            "timestamp": datetime.now().isoformat(),
            "is_correct": (
                predicted is not None
                and set(inv.reference for inv in predicted.invoices) == set(actual_invoice_refs)
            ),
        }

        # Generate features for training
        if actual_invoices:
            for inv in actual_invoices:
                features = compute_features(payment, inv)
                record["features"] = features
                record["label"] = 1  # positive match
                self._feedback_buffer.append(record.copy())

        # Check if we should trigger retraining
        if len(self._feedback_buffer) >= self.feedback_retrain_threshold:
            logger.info(
                "Feedback threshold reached (%d samples), triggering retrain",
                len(self._feedback_buffer),
            )

    def log_prediction(
        self,
        payment: Payment,
        result: MatchResult | None,
        feature_vector: dict[str, float] | None = None,
    ) -> None:
        """Log prediction for drift monitoring."""
        self._predictions_log.append({
            "payment_id": payment.id,
            "timestamp": datetime.now().isoformat(),
            "method": result.method.value if result else None,
            "confidence": result.confidence if result else 0.0,
            "layer": result.layer if result else -1,
            "features": feature_vector,
        })

    def check_drift(self, feature_name: str, current_values: np.ndarray) -> float:
        """Check data drift for a specific feature using PSI."""
        if feature_name not in self._feature_distributions:
            self._feature_distributions[feature_name] = current_values
            return 0.0

        reference = self._feature_distributions[feature_name]
        psi = compute_psi(reference, current_values)

        if psi > self.drift_threshold:
            logger.warning(
                "Data drift detected for %s: PSI=%.4f (threshold=%.4f)",
                feature_name, psi, self.drift_threshold,
            )

        return psi

    def should_retrain(self) -> tuple[bool, str]:
        """Determine if model retraining is needed."""
        # Check time since last training
        if self._training_history:
            last_train = self._training_history[-1]
            staleness = (datetime.now() - last_train.timestamp).days
            if staleness >= self.retrain_interval_days:
                return True, "scheduled"
        else:
            if self._feedback_buffer:
                return True, "initial"

        # Check feedback buffer size
        if len(self._feedback_buffer) >= self.feedback_retrain_threshold:
            return True, "feedback_threshold"

        # Check drift
        for feature_name, ref_dist in self._feature_distributions.items():
            recent = [
                p["features"].get(feature_name, 0)
                for p in self._predictions_log[-1000:]
                if p.get("features") and feature_name in p["features"]
            ]
            if len(recent) >= 100:
                psi = compute_psi(ref_dist, np.array(recent))
                if psi > self.drift_threshold:
                    return True, "drift"

        return False, ""

    def retrain(self, model: EnsembleModel) -> TrainingRecord | None:
        """Execute model retraining from accumulated feedback."""
        if not self._feedback_buffer:
            logger.warning("No feedback data for retraining")
            return None

        # Build training data from feedback
        feature_names = EnsembleModel.FEATURE_NAMES
        X_list = []
        y_list = []

        for record in self._feedback_buffer:
            if "features" in record and "label" in record:
                row = [record["features"].get(f, 0.0) for f in feature_names]
                X_list.append(row)
                y_list.append(record["label"])

        if len(X_list) < 50:
            logger.warning("Insufficient training data: %d samples", len(X_list))
            return None

        X = np.array(X_list)
        y = np.array(y_list)

        # Train
        metrics = model.train(X, y)

        # Save model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = str(self.model_dir / f"ensemble_{timestamp}.pkl")
        model.save(model_path)

        # Record
        trigger = self.should_retrain()[1] or "manual"
        record = TrainingRecord(
            timestamp=datetime.now(),
            n_samples=len(X),
            n_positive=int(y.sum()),
            metrics=metrics,
            model_path=model_path,
            trigger=trigger,
        )
        self._training_history.append(record)

        # Update reference distributions
        for i, name in enumerate(feature_names):
            self._feature_distributions[name] = X[:, i]

        # Clear feedback buffer
        self._feedback_buffer.clear()

        logger.info("Retrained model: %s", metrics)
        return record

    def compute_monitoring_metrics(
        self,
        pipeline_metrics: dict[str, Any],
        review_queue: HumanReviewQueue,
    ) -> MonitoringMetrics:
        """Compute all 13 monitoring metrics."""
        metrics = MonitoringMetrics()

        total = pipeline_metrics.get("total_payments", 0)
        if total == 0:
            return metrics

        metrics.auto_match_rate = pipeline_metrics.get("matched_auto", 0) / total
        metrics.avg_processing_time_ms = pipeline_metrics.get("avg_time_ms", 0)
        metrics.human_review_backlog = review_queue.queue_size

        # Layer distribution
        by_layer = pipeline_metrics.get("by_layer", {})
        for layer, count in by_layer.items():
            metrics.layer_distribution[layer] = count / total

        # Review stats
        stats = review_queue.stats
        metrics.avg_human_review_time_s = stats.get("avg_review_time_seconds", 0)

        # Precision/recall from feedback
        if self._feedback_buffer:
            correct = sum(1 for r in self._feedback_buffer if r.get("is_correct"))
            total_fb = len(self._feedback_buffer)
            metrics.precision = correct / max(total_fb, 1)

        # Model staleness
        if self._training_history:
            last = self._training_history[-1]
            metrics.model_staleness_days = (datetime.now() - last.timestamp).days

        # F1
        if metrics.precision > 0 and metrics.recall > 0:
            metrics.f1_score = 2 * metrics.precision * metrics.recall / (metrics.precision + metrics.recall)

        return metrics

    def export_metrics(self, metrics: MonitoringMetrics, path: str) -> None:
        """Export metrics to JSON for dashboard."""
        with open(path, "w") as f:
            json.dump(metrics.to_dict(), f, indent=2)
        logger.info("Metrics exported to %s", path)
