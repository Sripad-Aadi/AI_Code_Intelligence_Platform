"""SourceFile model — one row per indexed file in a repository (Step 5)."""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class SourceFile(Base):
    """A file that survived the Step-4 filters, recorded by the ingest task.

    `path` is relative to the repo clone root. `parse_error` captures per-file
    tree-sitter failures (so boundary-extraction accuracy is auditable) and is
    NULL when parsing was skipped (non-grammar text files) or succeeded.
    """

    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("repo_id", "path", name="uq_files_repo_path"),
        Index("ix_files_repo_id", "repo_id"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    path = Column(Text, nullable=False)  # clone-root-relative
    language = Column(String(64), nullable=False)
    line_count = Column(Integer, nullable=False, default=0)
    parse_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
