"""Per-repository risk prediction (Step 12 serve path).

Embeds every trainable symbol of one indexed repo with the same encoder the
training rows used, scales the engineered tail with the saved scaler, and
returns verdicts the findings router persists. Anything that needs a model
(`load_artifacts`) raises ``FileNotFoundError`` when nothing was trained —
the router turns that into "train first".
"""

import logging
from typing import Dict, List
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.embeddings.jina import embed_passages
from app.models.code_embedding import EMBEDDING_DIM
from app.models.file import SourceFile
from app.models.symbol import Symbol
from app.risk_model.dataset import TRAINABLE_KINDS
from app.risk_model.features import (
    N_ENGINEERED,
    as_vector,
    collect_test_paths,
    features_for_symbol,
    file_churn,
    file_fan,
    has_matching_test,
    repo_clone_root,
    symbol_text,
)
from app.risk_model.train import label_name, load_artifacts, model_version

log = logging.getLogger(__name__)

PREDICT_BATCH = 32


def predict_repo(db: Session, repo_id: UUID) -> List[Dict]:
    """Verdicts for every trainable symbol with retrievable source."""
    clf, scaler, _ = load_artifacts()
    version = model_version() or "unknown"

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
    files_by_id = {
        row.id: row
        for row in (db.query(SourceFile).filter(SourceFile.id.in_(file_ids)).all())
    }
    all_paths = [
        row[0]
        for row in (
            db.query(SourceFile.path).filter(SourceFile.repo_id == repo_id).all()
        )
    ]
    test_paths = collect_test_paths(all_paths)
    fan_in, fan_out = file_fan(db, repo_id)
    clone_root = repo_clone_root(db, repo_id)

    texts: List[str] = []
    order: List[int] = []
    feats: List[Dict] = []
    symbol_rows: List[Symbol] = []
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
        order.append(len(texts))
        texts.append(text)
        feats.append(feat)
        symbol_rows.append(symbol)

    verdicts = []
    for i in range(0, len(texts), PREDICT_BATCH):
        chunk = texts[i : i + PREDICT_BATCH]
        vectors = np.zeros((len(chunk), EMBEDDING_DIM + N_ENGINEERED))
        embeddings = embed_passages(chunk)
        for j, (text, feat) in enumerate(zip(chunk, feats[i : i + PREDICT_BATCH])):
            vectors[j, :EMBEDDING_DIM] = np.asarray(embeddings[j], dtype=float)
            vectors[j, EMBEDDING_DIM:] = np.asarray(as_vector(feat), dtype=float)
        scaled = vectors.copy()
        scaled[:, -N_ENGINEERED:] = scaler.transform(vectors[:, -N_ENGINEERED:])
        proba = clf.predict_proba(scaled)
        ids = np.argmax(proba, axis=1)
        for j, symbol in enumerate(symbol_rows[i : i + PREDICT_BATCH]):
            level = label_name(int(ids[j]))
            verdicts.append(
                {
                    "symbol_id": symbol.id,
                    "risk_level": level,
                    "probability": round(float(proba[j, ids[j]]), 4),
                    "features": feats[i + j],
                    "model_version": version,
                }
            )
    log.info(
        "risk predict: repo=%s symbols=%d version=%s", repo_id, len(verdicts), version
    )
    return verdicts
