"""Semantic code search API (Step 8).

Two endpoints, matching what the Search page offers as a mode switch:

- ``GET /repos/{repo_id}/search`` — one repository, the common case.
- ``GET /repos/search`` — every repository attached to the caller's projects.

Both answer with the top-k chunks from ``code_embeddings`` plus the metadata
the page renders as evidence (file path, symbol, exact line range): the plan's
"good embedding with bad metadata is useless" is exactly why each hit carries
``file_path``/``symbol_name``/``start_line``/``end_line``.

Ownership is enforced, not assumed: the single-repo route goes through
``_get_owned_repo``, and the cross-repo route *intersects* any requested
``repo_ids`` with the caller's own repositories, so asking for someone else's
repo id returns nothing rather than their code.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.ingestion import _get_owned_repo
from app.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.code_embedding import CodeEmbedding
from app.models.project import Project
from app.models.repository import ProjectRepository
from app.retrieval.search import DEFAULT_K, MAX_K, search_code

log = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


class SearchHit(BaseModel):
    """One retrieved chunk, with the metadata needed to cite it."""

    # Validate straight off the ORM `CodeEmbedding` row: pydantic v2 refuses
    # non-dict objects without `from_attributes` (it raised one validation
    # error per hit and the endpoint 500'd).
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repo_id: UUID
    file_id: Optional[UUID] = None
    file_path: str
    language: Optional[str] = None
    symbol_kind: Optional[str] = None
    symbol_name: Optional[str] = None
    start_line: int
    end_line: int
    content: str


class SearchResponse(BaseModel):
    query: str
    # "all" for the cross-repo route; the frontend only reads `hits`.
    repo_id: str
    hits: List[SearchHit]


def _owned_repo_ids(db: Session, current_user: CurrentUser) -> List[UUID]:
    """Ids of every repository attached to a project the caller owns."""
    rows = (
        db.query(ProjectRepository.id)
        .join(Project, Project.id == ProjectRepository.project_id)
        .filter(Project.owner_id == current_user.id)
        .all()
    )
    return [row[0] for row in rows]


def _parse_repo_ids(raw: Optional[str]) -> Optional[List[UUID]]:
    """Split the comma-separated `repo_ids` query parameter."""
    if not raw:
        return None
    parsed: List[UUID] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            parsed.append(UUID(part))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid repo_ids value: {part!r}"
            ) from None
    return parsed or None


def _run_search(
    db: Session,
    query: str,
    k: int,
    language: Optional[str],
    file_path: Optional[str],
    repo_id: Optional[UUID] = None,
    repo_ids: Optional[List[UUID]] = None,
) -> List[CodeEmbedding]:
    """Embed the query and rank chunks, translating failures into HTTP errors."""
    if not settings.EMBEDDING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail=(
                "Semantic search is unavailable: EMBEDDING_ENABLED=false, so "
                "there are no vectors to search."
            ),
        )

    # Distinguish "never indexed" from "no match": an unindexed repo would
    # otherwise render the same empty result as a genuinely bad query, which
    # is the silent failure this page used to have.
    if repo_id is not None:
        indexed = (
            db.query(func.count(CodeEmbedding.id))
            .filter(CodeEmbedding.repo_id == repo_id)
            .scalar()
            or 0
        )
        if indexed == 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This repository has no indexed chunks yet — run "
                    "Analyze on the project first."
                ),
            )

    try:
        return search_code(
            db,
            query=query,
            repo_id=repo_id,
            repo_ids=repo_ids,
            k=k,
            language=language,
            file_path=file_path,
        )
    except HTTPException:
        raise
    except Exception as exc:  # model load/encode failures, DB errors
        log.exception("semantic search failed (q=%r)", query[:60])
        raise HTTPException(status_code=502, detail=f"Search failed: {exc}") from exc


@router.get("/repos/{repo_id}/search", response_model=SearchResponse)
def search_repository(
    repo_id: UUID,
    q: str = Query(..., min_length=1, max_length=500),
    k: int = Query(DEFAULT_K, ge=1, le=MAX_K),
    language: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SearchResponse:
    """Top-k chunks for `q` inside one repository the caller owns."""
    _get_owned_repo(repo_id, current_user, db)
    hits = _run_search(
        db,
        query=q,
        k=k,
        language=language,
        file_path=file_path,
        repo_id=repo_id,
    )
    return SearchResponse(query=q, repo_id=str(repo_id), hits=hits)


@router.get("/repos/search", response_model=SearchResponse)
def search_all_repositories(
    q: str = Query(..., min_length=1, max_length=500),
    k: int = Query(DEFAULT_K, ge=1, le=MAX_K),
    language: Optional[str] = Query(default=None),
    repo_ids: Optional[str] = Query(
        default=None, description="Comma-separated repo ids to restrict to"
    ),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SearchResponse:
    """Top-k chunks for `q` across the caller's own repositories."""
    owned = _owned_repo_ids(db, current_user)
    if not owned:
        return SearchResponse(query=q, repo_id="all", hits=[])

    # Intersect rather than trust: `repo_ids` narrows the caller's own scope,
    # it never widens it.
    requested = _parse_repo_ids(repo_ids)
    scope = [rid for rid in owned if requested is None or rid in requested]
    if not scope:
        return SearchResponse(query=q, repo_id="all", hits=[])

    hits = _run_search(
        db,
        query=q,
        k=k,
        language=language,
        file_path=None,
        repo_ids=scope,
    )
    return SearchResponse(query=q, repo_id="all", hits=hits)
