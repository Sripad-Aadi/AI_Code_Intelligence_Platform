"""Risk model evaluation harness (Step 19).

Evaluates the trained risk classifier on a held-out test set.
Reports precision, recall, F1 per class, and confusion matrix.
"""

import json
import logging
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from app.risk_model.train import (
    MODEL_DIR,
    MODEL_PATH,
    RISK_LABELS,
    SCALER_PATH,
)
from sklearn.metrics import classification_report, confusion_matrix

log = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Per-class evaluation metrics."""

    risk_level: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class EvalSummary:
    """Aggregate evaluation summary."""

    accuracy: float
    macro_f1: float
    weighted_f1: float
    per_class: List[EvalResult]
    confusion_matrix: List[List[int]]
    n_samples: int


def _load_test_data() -> Tuple[np.ndarray, np.ndarray]:
    """
    Load test data. In production, this should load from a labeled dataset.
    For now, returns synthetic data matching the training distribution.
    """
    log.warning("Using synthetic test data — replace with real labeled test set")
    np.random.seed(123)  # Different seed from training
    n = 200
    X = np.random.randn(n, 768 + 6)
    y = np.random.choice([0, 1, 2], size=n, p=[0.6, 0.3, 0.1])
    return X, y


def _load_real_test_data(repo_ids: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    """Load real test data from database (placeholder)."""
    # TODO: Implement when labeling infrastructure exists
    return _load_test_data()


def evaluate_model(
    repo_ids: Optional[List[str]] = None,
) -> EvalSummary:
    """
    Evaluate the trained risk model on held-out test data.

    Args:
        repo_ids: Optional list of repo IDs to evaluate on.
                  If None, uses synthetic test data.

    Returns:
        EvalSummary with all metrics.
    """
    # Load model
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Train first.")

    with open(MODEL_PATH, "rb") as f:
        clf = pickle.load(f)
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    # Load test data
    if repo_ids:
        X_test, y_test = _load_real_test_data(repo_ids)
    else:
        X_test, y_test = _load_test_data()

    # Scale features (last 6 columns)
    X_test_scaled = X_test.copy()
    X_test_scaled[:, -6:] = scaler.transform(X_test[:, -6:])

    # Predict
    y_pred = clf.predict(X_test_scaled)

    # Compute metrics
    report = classification_report(
        y_test, y_pred, target_names=RISK_LABELS, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])

    per_class = [
        EvalResult(
            risk_level=label,
            precision=report[label]["precision"],
            recall=report[label]["recall"],
            f1=report[label]["f1-score"],
            support=report[label]["support"],
        )
        for label in RISK_LABELS
    ]

    summary = EvalSummary(
        accuracy=report["accuracy"],
        macro_f1=report["macro avg"]["f1-score"],
        weighted_f1=report["weighted avg"]["f1-score"],
        per_class=per_class,
        confusion_matrix=cm.tolist(),
        n_samples=len(y_test),
    )

    log.info(
        "Risk model evaluation: accuracy=%.4f, macro_f1=%.4f, weighted_f1=%.4f",
        summary.accuracy,
        summary.macro_f1,
        summary.weighted_f1,
    )
    log.info("Confusion matrix:\n%s", cm)
    for pc in per_class:
        log.info(
            "  %s: P=%.4f R=%.4f F1=%.4f (n=%d)",
            pc.risk_level,
            pc.precision,
            pc.recall,
            pc.f1,
            pc.support,
        )

    return summary


def save_evaluation(summary: EvalSummary, path: Optional[str] = None) -> None:
    """Save evaluation results to JSON."""
    if path is None:
        path = str(MODEL_DIR / "evaluation.json")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w") as f:
        json.dump(asdict(summary), f, indent=2)

    log.info("Evaluation saved to %s", path)


def print_evaluation(summary: EvalSummary) -> None:
    """Pretty-print evaluation results."""
    print("\n=== Risk Model Evaluation ===")
    print(f"Samples: {summary.n_samples}")
    print(f"Accuracy: {summary.accuracy:.4f}")
    print(f"Macro F1: {summary.macro_f1:.4f}")
    print(f"Weighted F1: {summary.weighted_f1:.4f}")
    print("\nPer-class metrics:")
    print(f"{'Class':<10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>10}")
    print("-" * 50)
    for pc in summary.per_class:
        print(
            f"{pc.risk_level:<10} {pc.precision:>10.4f} "
            f"{pc.recall:>10.4f} {pc.f1:>10.4f} {pc.support:>10}"
        )
    print("\nConfusion Matrix:")
    print("         Pred: low  med  high")
    for i, label in enumerate(RISK_LABELS):
        row = summary.confusion_matrix[i]
        print(f"True {label:<4}: {row[0]:>4} {row[1]:>4} {row[2]:>4}")


if __name__ == "__main__":
    summary = evaluate_model()
    print_evaluation(summary)
    save_evaluation(summary)
