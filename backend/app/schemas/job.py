"""Pydantic schemas for ingestion job status (Step 4 polling)."""

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalysisJobRead(BaseModel):
    """Public view of an AnalysisJob — what the polling endpoint returns."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repo_id: UUID
    status: str  # queued | running | completed | failed
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    files_scanned: int = 0
    files_indexed: int = 0
    symbols_indexed: int = 0
    languages: Optional[Dict[str, int]] = None
    created_at: datetime
