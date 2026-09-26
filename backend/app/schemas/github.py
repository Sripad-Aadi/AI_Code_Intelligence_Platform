"""Pydantic schemas for GitHub repo listing and attachment (Step 3)."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GitHubRepoSummary(BaseModel):
    """Slim projection of a GitHub repo for the /user/repos endpoint."""

    id: str
    full_name: str
    owner: str
    name: str
    default_branch: Optional[str] = None
    private: bool = False
    html_url: Optional[str] = None


class RepoAttachRequest(BaseModel):
    """Payload to attach + shallow-clone a GitHub repo to a project."""

    github_full_name: str = Field(
        ...,
        min_length=1,
        pattern=r"^[^/]+/[^/]+$",
        description="e.g. octocat/Hello-World",
    )
    branch: Optional[str] = None  # defaults to repo default_branch


class RepoAttachResponse(BaseModel):
    """Result of attaching + cloning a repo."""

    project_id: UUID
    github_repo_id: str
    github_owner: str
    github_name: str
    github_full_name: str
    default_branch: Optional[str] = None
    clone_path: str = Field(
        ..., description="Absolute path of the shallow clone on server disk"
    )
