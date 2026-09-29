"""Labeled dataset builder (Step 10): real symbols + synthetic top-up.

Real samples come from the caller's indexed repositories: every
function/class/method symbol becomes one sample with Step 10 features, a v1
weak label, and its jina embedding (the same model and normalisation as
retrieval, so train and serve live in one vector space). Twelve functions
cannot span three risk bands, so each class is topped up to
``MIN_PER_CLASS`` with seeded synthetic samples through the identical
feature and labeling code. The returned ``meta`` records exactly where every
sample came from — a dataset that cannot say how it was built is not one.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.embeddings.jina import embed_passages
from app.models.code_embedding import EMBEDDING_DIM
from app.models.file import SourceFile
from app.models.symbol import Symbol
from app.risk_model import labeling
from app.risk_model.features import (
    as_vector,
    collect_test_paths,
    features_for_symbol,
    file_churn,
    file_fan,
    has_matching_test,
    repo_clone_root,
    symbol_text,
)
from app.risk_model.labeling import LABEL_TO_ID, label_from_features

log = logging.getLogger(__name__)

# Symbols worth learning from: routes are FastAPI/Express decorators whose
# "complexity" is framework noise, not risk signal.
TRAINABLE_KINDS = ("function", "class", "method")

EMBED_BATCH = 32


@dataclass
class LabeledSample:
    """One training row with full provenance."""

    text: str
    features: Dict[str, float]
    label: str
    label_source: str  # heuristic-v1 | synthetic-v1 | manual
    repo_id: UUID | None = None
    symbol_id: UUID | None = None
    file_path: str = ""


@dataclass
class Dataset:
    """Built dataset: raw (unscaled) matrix, labels, and its own audit."""

    X: np.ndarray  # [embedding (768) | engineered (6)], unscaled
    y: np.ndarray  # label ids
    samples: List[LabeledSample] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)


def _real_samples(db: Session, repo_id: UUID) -> List[LabeledSample]:
    """Featurize every trainable symbol of one indexed repository."""
    symbols = (
        db.query(Symbol)
        .filter(
            Symbol.repo_id == repo_id,
            Symbol.kind.in_(TRAINABLE_KINDS),
        )
        .order_by(Symbol.name)
        .all()
    )
    if not symbols:
        return []
    file_ids = {symbol.file_id for symbol in symbols}
    files = (
        db.query(SourceFile).filter(SourceFile.id.in_(file_ids)).all()
        if file_ids
        else []
    )
    files_by_id = {row.id: row for row in files}
    all_paths = [
        row[0]
        for row in (
            db.query(SourceFile.path).filter(SourceFile.repo_id == repo_id).all()
        )
    ]
    test_paths = collect_test_paths(all_paths)
    fan_in, fan_out = file_fan(db, repo_id)
    clone_root = repo_clone_root(db, repo_id)

    samples = []
    for symbol in symbols:
        file_row = files_by_id.get(symbol.file_id)
        if file_row is None:
            continue
        text = symbol_text(db, repo_id, file_row, symbol)
        if not text or not text.strip():
            continue
        feat = features_for_symbol(
            db,
            repo_id,
            file_row,
            symbol,
            text,
            fan_in=fan_in.get(file_row.id, 0),
            fan_out=fan_out.get(file_row.id, 0),
            has_test=has_matching_test(file_row.path, test_paths),
            churn=file_churn(clone_root, file_row.path),
        )
        samples.append(
            LabeledSample(
                text=text,
                features=feat,
                label=label_from_features(feat),
                label_source="heuristic-v1",
                repo_id=repo_id,
                symbol_id=symbol.id,
                file_path=file_row.path,
            )
        )
    return samples


def _synthetic_samples(need: Dict[str, int]) -> List[LabeledSample]:
    """Top-up samples through the identical feature + labeling code."""
    from app.risk_model.labeling import generate_synthetic, synthetic_features

    samples = []
    for label in labeling.LABELS:
        count = need.get(label, 0)
        if count <= 0:
            continue
        kwargs = {"n_low": 0, "n_medium": 0, "n_high": 0}
        kwargs[f"n_{label}"] = count
        for item in generate_synthetic(**kwargs):
            feat, actual = synthetic_features(item)
            samples.append(
                LabeledSample(
                    text=item.code,
                    features=feat,
                    label=actual,
                    label_source=item.label_source,
                    file_path=f"synthetic/{label}.py",
                )
            )
    return samples


def build_dataset(db: Session, repo_ids: List[UUID]) -> Dataset:
    """Build the labeled dataset: real symbols first, synthetic top-up."""
    started = time.perf_counter()
    real: List[LabeledSample] = []
    for repo_id in repo_ids:
        real.extend(_real_samples(db, repo_id))
    real_counts = {label: 0 for label in labeling.LABELS}
    for sample in real:
        real_counts[sample.label] += 1

    need = labeling.top_up_counts(real_counts)
    synthetic = _synthetic_samples(need)
    syn_counts = {label: 0 for label in labeling.LABELS}
    for sample in synthetic:
        syn_counts[sample.label] += 1

    samples = real + synthetic
    texts = [sample.text for sample in samples]
    embeddings: List[List[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        embeddings.extend(embed_passages(texts[i : i + EMBED_BATCH]))

    X = np.zeros((len(samples), EMBEDDING_DIM + len(as_vector(samples[0].features))))
    y = np.zeros(len(samples), dtype=int)
    for i, sample in enumerate(samples):
        X[i, :EMBEDDING_DIM] = np.asarray(embeddings[i], dtype=float)
        X[i, EMBEDDING_DIM:] = np.asarray(as_vector(sample.features), dtype=float)
        y[i] = LABEL_TO_ID[sample.label]

    meta = {
        "label_version": labeling.LABEL_VERSION,
        "n_real": len(real),
        "n_synthetic": len(synthetic),
        "real_counts": real_counts,
        "synthetic_counts": syn_counts,
        "synthetic_requested": need,
        "repo_ids": [str(rid) for rid in repo_ids],
        "build_seconds": round(time.perf_counter() - started, 1),
    }
    log.info(
        "risk dataset: %d real + %d synthetic %s (%.1fs)",
        len(real),
        len(synthetic),
        syn_counts,
        meta["build_seconds"],
    )
    return Dataset(X=X, y=y, samples=samples, meta=meta)


def label_ids_to_names(ids) -> List[str]:
    return [labeling.LABELS[int(i)] for i in ids]
