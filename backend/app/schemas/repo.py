"""Pydantic schemas for ProjectRepository API."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
