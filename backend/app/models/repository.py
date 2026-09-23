"""ProjectRepository model — links a project to a GitHub repository."""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ProjectRepository(Base):
    """Association between a Project and a GitHub repository.

    In Step 2 this is a placeholder (no GitHub data yet). Step 3 will populate
    the GitHub-specific fields when the user attaches a real repository.
    """

    __tablename__ = "project_repositories"
    __table_args__ = (
        UniqueConstraint("project_id", "github_repo_id", name="uq_project_github_repo"),
        Index("ix_project_repositories_project_id", "project_id"),
        Index("ix_project_repositories_github_repo_id", "github_repo_id"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    github_repo_id = Column(
        String(100), nullable=True
    )  # GitHub's numeric repo ID (string for safety)
    github_owner = Column(String(255), nullable=True)  # e.g., "octocat"
    github_name = Column(String(255), nullable=True)  # e.g., "Hello-World"
    github_full_name = Column(String(512), nullable=True)  # "octocat/Hello-World"
    default_branch = Column(String(255), nullable=True)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    project = relationship("Project", back_populates="repositories")
