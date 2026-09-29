"""PR analysis API (Step 14).

* ``GET /repos/{repo_id}/pulls`` lists open PRs so the dashboard is
  reachable without knowing a PR number off-hand.
* ``GET /repos/{repo_id}/prs/{pr_number}/analysis`` runs the full chain on
  demand: PR metadata + diff from GitHub, symbol mapping, 1-hop affected
  files, test heuristic, risk scores, LLM summary. Synchronous and
  unpersisted by design — the result is derived data (recomputed from the
  index + GitHub), and the Celery task already covers the webhook flow.

Failures are distinguishable: 404 unknown repo/PR, 409 GitHub not linked,
429 rate limit, 502 GitHub/provider failure. The LLM summary degrades (empty
summary, structural data kept) rather than failing the whole analysis.
"""

import asyncio
import logging
from typing import List
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.ingestion import _get_owned_repo
from app.core.rate_limit import pr_analysis_rate_limit
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.pr_analysis.chain import PRAnalysisResult, run_pr_analysis
from app.services import github as github_service

log = logging.getLogger(__name__)

router = APIRouter(tags=["pull_requests"])


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str | None = None
    head_ref: str | None = None
    base_ref: str | None = None
    html_url: str | None = None


def _owner_github_token(db: Session, repo_id: UUID) -> tuple:
    """(owner, name, token) for GitHub API calls, or 409 when unlinked."""
    from app.models.repository import ProjectRepository

    repo = db.get(ProjectRepository, repo_id)
    project = db.get(Project, repo.project_id) if repo else None
    owner = db.get(User, project.owner_id) if project else None
    token = owner.github_access_token if owner else None
    if repo is None or not repo.github_owner or not token:
        raise HTTPException(
            status_code=409,
            detail="GitHub is not linked for this repository's owner — "
            "link it on the dashboard first.",
        )
    return repo.github_owner, repo.github_name, token


def _github_error(action: str, exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 404:
            return HTTPException(status_code=404, detail=f"PR not found ({action})")
        if status in (401, 403):
            # The stored OAuth token is dead (revoked/expired) — retrying
            # changes nothing, so say exactly what to do instead of 502.
            return HTTPException(
                status_code=409,
                detail=(
                    "GitHub rejected the stored token — re-link GitHub on "
                    "the dashboard, then try again."
                ),
            )
    log.warning("GitHub API failed (%s): %s", action, exc)
    return HTTPException(status_code=502, detail=f"GitHub API failed ({action})")


@router.get("/repos/{repo_id}/pulls", response_model=List[PullRequestSummary])
def list_pulls(
    repo_id: UUID,
    state: str = Query(default="open", pattern="^(open|closed|all)$"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(pr_analysis_rate_limit),
) -> List[PullRequestSummary]:
    """Open pull requests for one owned repository (dashboard entry)."""
    repo = _get_owned_repo(repo_id, current_user, db)
    owner, name, token = _owner_github_token(db, repo.id)
    try:
        pulls = github_service.list_pull_requests(token, owner, name, state=state)
    except Exception as exc:
        raise _github_error("list pulls", exc)
    return [PullRequestSummary(**pull) for pull in pulls]


@router.get(
    "/repos/{repo_id}/prs/{pr_number}/analysis",
    response_model=PRAnalysisResult,
)
def analyze_pull_request(
    repo_id: UUID,
    pr_number: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(pr_analysis_rate_limit),
) -> PRAnalysisResult:
    """Run the Step 14 chain for one PR and return structured JSON."""
    repo = _get_owned_repo(repo_id, current_user, db)
    owner, name, token = _owner_github_token(db, repo.id)
    try:
        meta = github_service.get_pull_request(token, owner, name, pr_number)
    except Exception as exc:
        raise _github_error("fetch PR", exc)
    try:
        return asyncio.run(
            run_pr_analysis(
                db,
                repo_id=repo.id,
                pr_number=pr_number,
                pr_title=meta["title"],
                pr_body=meta["body"],
                head_sha=meta["head_sha"],
                base_sha=meta["base_sha"],
                access_token=token,
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("PR analysis failed (repo=%s pr=%d)", repo.id, pr_number)
        raise HTTPException(
            status_code=502, detail=f"PR analysis failed: {exc}"
        ) from exc
