"""ImportStatement model — raw import records from a file (Step 5)."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class ImportStatement(Base):
    """One import statement seen in a file.

    `module` is the raw specifier (e.g. `os`, `./utils`, `@angular/core`).
    `resolved_path` is the best-effort repo-relative path the import points at
    when it is local to the repo (None for stdlib/external packages) — edges
    are created after the whole repo is walked when that file exists.
    """

    __tablename__ = "imports"
    __table_args__ = (Index("ix_imports_repo_id", "repo_id"),)

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    module = Column(String(1024), nullable=False)
    is_relative = Column(Boolean, nullable=False, default=False)
    resolved_path = Column(String(2048), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
