"""Risk findings API (Step 12).

Reads the verdicts the last training run persisted: a filtered,
paginated list plus a per-level summary for the Findings page header.
Both return empty results (not 404) when a repo was never scored — an
unscored repo is a normal state, not an error, and the page renders it.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.ingestion import _get_owned_repo
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.file import SourceFile
from app.models.risk_finding import RiskFinding
from app.models.symbol import Symbol
from app.schemas.risk import FindingsSummary, RiskFindingListResponse, RiskFindingRead

log = logging.getLogger(__name__)

router = APIRouter(tags=["findings"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.get("/repos/{repo_id}/findings", response_model=RiskFindingListResponse)
def list_findings(
    repo_id: UUID,
    risk_level: Optional[str] = Query(default=None, pattern="^(low|medium|high)$"),
    min_probability: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RiskFindingListResponse:
    """List one repo's risk findings, newest first, with filters."""
    repo = _get_owned_repo(repo_id, current_user, db)
    query = db.query(RiskFinding).filter(RiskFinding.repo_id == repo.id)
    if risk_level is not None:
        query = query.filter(RiskFinding.risk_level == risk_level)
    if min_probability is not None:
        query = query.filter(RiskFinding.probability >= min_probability)
    total = query.count()
    rows = (
        query.order_by(RiskFinding.probability.desc()).limit(limit).offset(offset).all()
    )
    # Display context in one join: symbol/file rows cannot be missing
    # (both FKs are ON DELETE CASCADE), so an inner join is exact.
    info = {
        finding.id: (symbol, file_row)
        for finding, symbol, file_row in (
            db.query(RiskFinding, Symbol, SourceFile)
            .join(Symbol, Symbol.id == RiskFinding.symbol_id)
            .join(SourceFile, SourceFile.id == Symbol.file_id)
            .filter(RiskFinding.id.in_([row.id for row in rows]))
            .all()
        )
    }
    findings = []
    for row in rows:
        symbol, file_row = info.get(row.id, (None, None))
        findings.append(
            RiskFindingRead(
                id=row.id,
                repo_id=row.repo_id,
                symbol_id=row.symbol_id,
                risk_level=row.risk_level,
                probability=row.probability,
                features_json=row.features_json or {},
                model_version=row.model_version,
                created_at=row.created_at,
                updated_at=row.updated_at,
                symbol_name=symbol.name if symbol else "",
                symbol_kind=symbol.kind if symbol else "",
                file_path=file_row.path if file_row else "",
                start_line=symbol.start_line if symbol else 0,
                end_line=symbol.end_line if symbol else 0,
            )
        )
    return RiskFindingListResponse(
        repo_id=repo.id, findings=findings, total=total, limit=limit, offset=offset
    )


@router.get("/repos/{repo_id}/findings/summary", response_model=FindingsSummary)
def findings_summary(
    repo_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FindingsSummary:
    """Per-level counts for one repo; every level is always present."""
    repo = _get_owned_repo(repo_id, current_user, db)
    rows = (
        db.query(RiskFinding.risk_level, func.count(RiskFinding.id))
        .filter(RiskFinding.repo_id == repo.id)
        .group_by(RiskFinding.risk_level)
        .all()
    )
    by_level = {"low": 0, "medium": 0, "high": 0}
    for level, count in rows:
        if level in by_level:
            by_level[level] = count
    return FindingsSummary(
        repo_id=repo.id, by_level=by_level, total=sum(by_level.values())
    )
