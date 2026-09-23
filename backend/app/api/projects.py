"""Project API routes: CRUD for projects and repository attachments."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.security import CurrentUser, get_current_user, require_project_owner
from app.db.session import get_db
from app.models.project import Project
from app.models.repository import ProjectRepository
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


# --- Repository attachments (placeholders for Step 2, populated in Step 3) ---


@router.post(
    "/{project_id}/repositories",
    response_model=ProjectRepositoryRead,
    status_code=status.HTTP_201_CREATED,
)
def attach_repository(
    project_id: UUID,
    payload: ProjectRepositoryRead,  # reuse read schema for create
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_project_owner),
) -> ProjectRepository:
    """Attach a repository placeholder to a project.

    In Step 2 this accepts optional GitHub metadata fields.
    Step 3 will replace this with GitHub OAuth-driven attachment.
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repo = ProjectRepository(
        project_id=project_id,
        github_repo_id=payload.github_repo_id,
        github_owner=payload.github_owner,
        github_name=payload.github_name,
        github_full_name=payload.github_full_name,
        default_branch=payload.default_branch,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


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
