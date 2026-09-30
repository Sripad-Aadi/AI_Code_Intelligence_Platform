"""Repository API routes (Step 3: GitHub repo listing + attachments).

`GET /user/repos` lists the caller's GitHub-accessible repositories using the
token stored on their user row by the OAuth callback. `POST /projects/{id}/repos`
attaches one and shallow-clones it (see app/api/projects.py).
"""

from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.github import GitHubRepoSummary
from app.services import github

router = APIRouter(tags=["repositories"])


def _require_linked_user(db: Session, current_user: CurrentUser) -> User:
    """Return the caller's user row, requiring a linked GitHub account."""
    user = db.get(User, current_user.id)
    if not user or not user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=(
                "GitHub not linked. Call GET /auth/github/login?state=<supabase-jwt> "
                "and complete the OAuth flow first."
            ),
        )
    return user


@router.get("/user/repos", response_model=List[GitHubRepoSummary])
async def list_github_repos(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """List GitHub repositories the user can access (owner + collaborator)."""
    user = _require_linked_user(db, current_user)
    try:
        return github.list_user_repos(user.github_access_token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            # The stored OAuth token is dead (revoked/expired) — retrying
            # changes nothing, so say exactly what to do instead of 502.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "GitHub rejected the stored token — re-link GitHub on "
                    "the Profile page, then try again."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {exc}",
        )
    except Exception as e:  # httpx errors / GitHub 5xx
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {e}",
        )


@router.get("/repos", response_model=List[dict])
def list_attached_repos(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """List all repositories attached across the caller's projects."""
    from app.models.project import Project
    from app.models.repository import ProjectRepository

    rows = (
        db.query(ProjectRepository)
        .join(Project, Project.id == ProjectRepository.project_id)
        .filter(Project.owner_id == current_user.id)
        .order_by(ProjectRepository.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "github_full_name": r.github_full_name,
            "default_branch": r.default_branch,
            "last_indexed_at": r.last_indexed_at.isoformat()
            if r.last_indexed_at
            else None,
        }
        for r in rows
    ]
