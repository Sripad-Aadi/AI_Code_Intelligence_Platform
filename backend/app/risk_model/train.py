"""Risk classifier training (Step 11).

Input vector = jina embedding (768-d) concatenated with the six engineered
features — the plan's layout, which ``risk_eval.py`` also assumes ("scale
the last 6 columns"). Only the engineered tail is standardized; the
embedding is already L2-normalised by the encoder and must not be
re-scaled. Two classifier choices (the RiskTraining page offers both):

* ``logistic`` — L2 logistic regression (fast, interpretable, the default).
* ``gbt`` — gradient boosting (non-linear, slower to train).

Artifacts live under ``MODEL_DIR`` and are loaded with plain pickle so the
Step 19 eval harness (which predates this module and imports these names)
keeps working: ``MODEL_PATH``/``SCALER_PATH`` plus ``META_PATH`` (versions,
dataset audit, test metrics) and ``TEST_SPLIT_PATH`` (the held-out split,
so evaluate measures the same rows train held out — same seed, no DB).
"""

import json
import logging
import pickle
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app.risk_model.dataset import build_dataset
from app.risk_model.features import N_ENGINEERED

log = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = MODEL_DIR / "model.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
META_PATH = MODEL_DIR / "meta.json"
TEST_SPLIT_PATH = MODEL_DIR / "test_split.npz"

RISK_LABELS = ["low", "medium", "high"]

MODEL_TYPES = ("logistic", "gbt")
TEST_FRACTION = 0.2
SPLIT_SEED = 20260928


def fit_classifier(X_train: np.ndarray, y_train: np.ndarray, model_type: str):
    """Fit one classifier — pure numpy in, fitted model out (unit-tested)."""
    if model_type == "gbt":
        clf = GradientBoostingClassifier(random_state=SPLIT_SEED)
    elif model_type == "logistic":
        clf = LogisticRegression(max_iter=2000)
    else:
        raise ValueError(f"unknown model_type {model_type!r}; want {MODEL_TYPES}")
    clf.fit(X_train, y_train)
    return clf


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(
            float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4
        ),
    }


def train_model(
    db: Session, repo_ids: List[UUID], model_type: str = "logistic"
) -> Dict:
    """Build the dataset, train, persist artifacts, return the report."""
    if model_type not in MODEL_TYPES:
        raise ValueError(f"unknown model_type {model_type!r}; want {MODEL_TYPES}")
    started = time.perf_counter()

    dataset = build_dataset(db, repo_ids)
    n = len(dataset.y)
    indices = np.arange(n)
    train_idx, test_idx = train_test_split(
        indices,
        test_size=TEST_FRACTION,
        random_state=SPLIT_SEED,
        stratify=dataset.y,
    )
    X_train, X_test = dataset.X[train_idx], dataset.X[test_idx]
    y_train, y_test = dataset.y[train_idx], dataset.y[test_idx]

    n_eng = N_ENGINEERED
    scaler = StandardScaler()
    X_train_scaled = X_train.copy()
    X_test_scaled = X_test.copy()
    X_train_scaled[:, -n_eng:] = scaler.fit_transform(X_train[:, -n_eng:])
    X_test_scaled[:, -n_eng:] = scaler.transform(X_test[:, -n_eng:])

    clf = fit_classifier(X_train_scaled, y_train, model_type)
    train_metrics = _metrics(y_train, clf.predict(X_train_scaled))
    test_metrics = _metrics(y_test, clf.predict(X_test_scaled))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    # Saved *unscaled*: every consumer (evaluate endpoint, risk_eval harness)
    # scales exactly once with the saved scaler. Saving the scaled copy
    # caused double-scaling — evaluate reported different numbers than train.
    np.savez_compressed(TEST_SPLIT_PATH, X_test=X_test, y_test=y_test)
    version = f"{model_type}-v1"
    meta = {
        "model_version": version,
        "model_type": model_type,
        "labels": RISK_LABELS,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "dataset": dataset.meta,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    elapsed = round(time.perf_counter() - started, 1)
    log.info(
        "risk train: %s on %d samples (%ds): test acc=%.4f macro_f1=%.4f",
        version,
        n,
        elapsed,
        test_metrics["accuracy"],
        test_metrics["macro_f1"],
    )
    return {
        "model_version": version,
        "n_samples": n,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "dataset": dataset.meta,
        "elapsed_seconds": elapsed,
    }


def load_artifacts() -> Tuple:
    """Load (classifier, scaler, meta); FileNotFoundError means train first."""
    if not MODEL_PATH.exists() or not SCALER_PATH.exists():
        raise FileNotFoundError(f"no trained model at {MODEL_PATH}; train first")
    with open(MODEL_PATH, "rb") as f:
        clf = pickle.load(f)
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)
    meta = {}
    if META_PATH.exists():
        with open(META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
    return clf, scaler, meta


def load_test_split() -> Tuple[np.ndarray, np.ndarray]:
    """Held-out split saved at train time (evaluate measures the same rows)."""
    if not TEST_SPLIT_PATH.exists():
        raise FileNotFoundError("no test split saved; train first")
    with np.load(TEST_SPLIT_PATH) as split:
        return split["X_test"], split["y_test"]


def predict_proba_vectors(vectors: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Class ids + max probabilities for scaled input rows."""
    clf, scaler, meta = load_artifacts()
    rows = np.asarray(vectors, dtype=float).copy()
    rows[:, -N_ENGINEERED:] = scaler.transform(rows[:, -N_ENGINEERED:])
    proba = clf.predict_proba(rows)
    ids = np.argmax(proba, axis=1)
    return ids, proba[np.arange(len(rows)), ids]


def label_name(label_id: int) -> str:
    return RISK_LABELS[int(label_id)]


def model_version() -> Optional[str]:
    try:
        _, _, meta = load_artifacts()
    except FileNotFoundError:
        return None
    return meta.get("model_version")
