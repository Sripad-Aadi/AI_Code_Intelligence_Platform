"""Project API routes: CRUD for projects and repository attachments."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.core.security import CurrentUser, get_current_user, require_project_owner
from app.db.session import get_db
from app.models.project import Project
from app.models.repository import ProjectRepository
from app.schemas.github import RepoAttachRequest
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectWithRepos,
)
from app.schemas.repo import ProjectRepositoryRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Project:
    """Create a new project for the authenticated user."""
    project = Project(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[Project]:
    """List all projects owned by the authenticated user."""
    return (
        db.query(Project)
        .filter(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.get("/{project_id}", response_model=ProjectWithRepos)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> Project:
    """Get a project with its repositories (owner only)."""
    project = (
        db.query(Project)
        .options(selectinload(Project.repositories))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> Project:
    """Update a project's name or description (owner only)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> None:
    """Delete a project and all its repositories (owner only)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


# --- Repository attachments (Step 3: GitHub-driven attach + shallow clone) ---


@router.post(
    "/{project_id}/repositories",
    response_model=ProjectRepositoryRead,
    status_code=status.HTTP_201_CREATED,
)
def attach_repository(
    project_id: UUID,
    payload: RepoAttachRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> ProjectRepository:
    """Attach a GitHub repo to a project and shallow-clone it to server disk.

    Uses the GitHub token stored on the caller's user row (see /auth/github/*).
    The clone lands in CLONE_ROOT_DIR; metadata (owner/name/default_branch/
    last_indexed_at) is persisted in project_repositories.
    """
    from app.ingestion.clone import clone_shallow
    from app.models.user import User
    from app.services import github

    # Pull the full user row to get the stored GitHub access token.
    user_row = db.get(User, current_user.id)
    if not user_row or not user_row.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=(
                "GitHub not linked. Complete GET /auth/github/login?state=<jwt> "
                "first (see /auth/github/callback)."
            ),
        )

    # 1. Look up the repository on GitHub to get authoritative metadata.
    try:
        repo = github.get_repo(user_row.github_access_token, payload.github_full_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error resolving repo: {e}",
        )

    # 2. Insert metadata in Postgres.
    repo_row = ProjectRepository(
        project_id=project_id,
        github_repo_id=repo["id"],
        github_owner=repo["owner"],
        github_name=repo["name"],
        github_full_name=repo["full_name"],
        default_branch=payload.branch or repo.get("default_branch"),
        last_indexed_at=None,  # set below once the clone lands
    )
    db.add(repo_row)
    db.commit()
    db.refresh(repo_row)

    # 3. Shallow clone to server disk (depth=1). Use the token in the URL so
    #    private repos work too.
    clone_url = repo["clone_url"].replace(
        "https://", f"https://x-access-token:{user_row.github_access_token}@"
    )
    dest = (
        Path(settings.CLONE_ROOT_DIR)
        / str(project_id)
        / repo["full_name"].replace("/", "__")
    )
    try:
        clone_shallow(clone_url, dest)
    except Exception as e:
        repo_row.last_indexed_at = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shallow clone failed: {e}",
        )

    # 4. Mark indexed and return.
    repo_row.last_indexed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(repo_row)
    return repo_row


@router.get(
    "/{project_id}/repositories",
    response_model=List[ProjectRepositoryRead],
)
def list_repositories(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> List[ProjectRepository]:
    """List all repositories attached to a project (owner only)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.repositories


@router.delete(
    "/{project_id}/repositories/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_repository(
    project_id: UUID,
    repo_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> None:
    """Detach a repository from a project (owner only)."""
    repo = db.get(ProjectRepository, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repository not found")
    db.delete(repo)
    db.commit()
