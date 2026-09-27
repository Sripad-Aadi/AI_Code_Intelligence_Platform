"""AnalysisJob model — one row per ingestion/analysis run on a repository."""

import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base

# Job lifecycle states (mirrored in schemas/job.py for the API contract).
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"


class AnalysisJob(Base):
    """Track the lifecycle of a repository ingestion (queued → running → done).

    The Celery worker updates this row as it walks the clone; the API's
    polling endpoint (`GET /jobs/{id}`) reads it so the frontend can show
    progress while ingestion runs.
    """

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_repo_id", "repo_id"),
        Index("ix_analysis_jobs_status", "status"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default=JOB_QUEUED)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    files_scanned = Column(Integer, nullable=False, default=0)
    files_indexed = Column(Integer, nullable=False, default=0)
    symbols_indexed = Column(Integer, nullable=False, default=0, server_default="0")
    chunks_indexed = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Step 7: chunks embedded into code_embeddings",
    )
    languages = Column(JSON, nullable=True)  # {"Python": 12, "TypeScript": 4, ...}
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
