"""Risk model training API (Steps 11 + 15 surface).

* ``POST /risk/train`` builds the labeled dataset from the caller's indexed
  repos (real symbols first, seeded synthetic top-up per class), trains the
  requested classifier, persists artifacts, and scores the trained repos so
  the Findings page has rows to show. Synchronous: the dataset is small
  (a few hundred samples) and the page awaits the POST.
* ``POST /risk/evaluate`` re-scores the held-out split saved at train time
  (same rows, no DB) and reports accuracy + macro F1.

``repo_ids`` is optional: omitted means every repository on the caller's
projects (intersected, like the cross-repo search — asking for someone
else's repo id trains on nothing of theirs).
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sklearn.metrics import accuracy_score, f1_score
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.repository import ProjectRepository
from app.models.risk_finding import RiskFinding
from app.risk_model.features import N_ENGINEERED
from app.risk_model.predict import predict_repo
from app.risk_model.train import (
    MODEL_TYPES,
    load_artifacts,
    load_test_split,
    train_model,
)
from app.schemas.risk import EvaluateResponse, TrainResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["risk"])


def _caller_repo_ids(
    db: Session, current_user: CurrentUser, requested: Optional[List[UUID]]
) -> List[UUID]:
    """Owned repo ids, intersected with any requested subset."""
    project_ids = [
        row[0]
        for row in (
            db.query(Project.id).filter(Project.owner_id == current_user.id).all()
        )
    ]
    if not project_ids:
        return []
    owned = [
        row[0]
        for row in (
            db.query(ProjectRepository.id)
            .filter(ProjectRepository.project_id.in_(project_ids))
            .all()
        )
    ]
    if requested is None:
        return owned
    wanted = set(requested)
    return [rid for rid in owned if rid in wanted]


def _parse_repo_ids(raw: Optional[str]) -> Optional[List[UUID]]:
    if not raw:
        return None
    try:
        return [UUID(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="repo_ids must be UUIDs")


@router.post("/risk/train", response_model=TrainResponse)
def train_risk(
    repo_ids: Optional[str] = Query(default=None),
    model_type: str = Query(default="logistic"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TrainResponse:
    """Train the 3-class risk classifier and score the trained repos."""
    if model_type not in MODEL_TYPES:
        raise HTTPException(
            status_code=422, detail=f"unknown model_type; want one of {MODEL_TYPES}"
        )
    owned = _caller_repo_ids(db, current_user, _parse_repo_ids(repo_ids))
    if not owned:
        raise HTTPException(status_code=409, detail="no owned repositories to train on")
    try:
        report = train_model(db, owned, model_type=model_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("risk train failed")
        raise HTTPException(status_code=502, detail=f"training failed: {exc}") from exc

    scored = 0
    written = 0
    for repo_id in owned:
        try:
            verdicts = predict_repo(db, repo_id)
        except Exception:
            log.exception("risk scoring failed (repo=%s)", repo_id)
            continue
        db.query(RiskFinding).filter(RiskFinding.repo_id == repo_id).delete()
        for verdict in verdicts:
            db.add(
                RiskFinding(
                    repo_id=repo_id,
                    symbol_id=verdict["symbol_id"],
                    risk_level=verdict["risk_level"],
                    probability=verdict["probability"],
                    features_json=verdict["features"],
                    model_version=verdict["model_version"],
                )
            )
        scored += 1
        written += len(verdicts)
    db.commit()

    dataset = report["dataset"]
    test = report["test_metrics"]
    message = (
        f"trained {report['model_version']} on {report['n_samples']} samples "
        f"({dataset['n_real']} real + {dataset['n_synthetic']} synthetic, "
        f"{dataset['build_seconds']}s embed) in {report['elapsed_seconds']}s; "
        f"test acc={test['accuracy']} macro_f1={test['macro_f1']}; "
        f"scored {scored} repo(s), {written} finding(s) written"
    )
    return TrainResponse(ok=True, message=message)


@router.post("/risk/evaluate", response_model=EvaluateResponse)
def evaluate_risk(
    repo_ids: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EvaluateResponse:
    """Score the held-out split from the last training run."""
    # `repo_ids` is accepted for the page's contract, but the split is fixed
    # at train time — evaluation always measures those same rows.
    if repo_ids is not None:
        _parse_repo_ids(repo_ids)
    try:
        clf, scaler, meta = load_artifacts()
        X_test, y_test = load_test_split()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=f"{exc}; train first") from exc
    rows = X_test.copy()
    rows[:, -N_ENGINEERED:] = scaler.transform(X_test[:, -N_ENGINEERED:])
    y_pred = clf.predict(rows)
    acc = round(float(accuracy_score(y_test, y_pred)), 4)
    macro = round(float(f1_score(y_test, y_pred, average="macro", zero_division=0)), 4)
    version = meta.get("model_version", "unknown")
    return EvaluateResponse(
        ok=True,
        message=(
            f"{version}: {len(y_test)} held-out samples, "
            f"accuracy={acc} macro_f1={macro}"
        ),
    )
