"""CodeEdge model — shallow relationships: file→file imports, symbol→file."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class CodeEdge(Base):
    """A directed relationship between two rows.

    Shallow v1 graph per the plan:
      - edge_type "imports":   source is a file, target is the imported file.
      - edge_type "belongs_to": source is a symbol, target is its file.
    Call-graph tracing is deferred to V3, so no other edge types exist yet.
    """

    __tablename__ = "edges"
    __table_args__ = (
        Index("ix_edges_repo_id_type", "repo_id", "edge_type"),
        Index("ix_edges_source", "source_id"),
        Index("ix_edges_target", "target_id"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_kind = Column(String(20), nullable=False)  # file | symbol
    source_id = Column(PG_UUID(as_uuid=True), nullable=False)  # no polymorphic FK
    edge_type = Column(String(20), nullable=False)  # imports | belongs_to
    target_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
