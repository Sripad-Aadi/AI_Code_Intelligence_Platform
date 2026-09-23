"""Pydantic schemas for Project API."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectWithRepos(ProjectRead):
    repositories: list["ProjectRepositoryRead"] = []


class ProjectRepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    github_repo_id: Optional[str] = None
    github_owner: Optional[str] = None
    github_name: Optional[str] = None
    github_full_name: Optional[str] = None
    default_branch: Optional[str] = None
    last_indexed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


ProjectWithRepos.model_rebuild()
