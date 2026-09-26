"""Symbol model — function/class/method/route boundaries from tree-sitter."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class Symbol(Base):
    """A named code entity with its line span, extracted from one file.

    `kind` is one of: function, class, method, route. start/end lines are
    1-based and inclusive — Step 7 chunks exactly these spans for embedding.
    """

    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbols_repo_id_kind", "repo_id", "kind"),
        Index("ix_symbols_file_id", "file_id"),
    )

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
    kind = Column(String(20), nullable=False)  # function|class|method|route
    name = Column(String(512), nullable=False)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
