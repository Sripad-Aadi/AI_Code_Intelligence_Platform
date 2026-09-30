"""Step 19 — Observability API endpoints.

Provides endpoints for:
- Structured log viewing (correlation ID search)
- Benchmark results (retrieval + risk evaluation)
- System metrics (job stats, latency, costs)
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.cost_tracking import get_cost_tracker
from app.core.rate_limit import create_rate_limiter
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.job import AnalysisJob

router = APIRouter(prefix="/observability", tags=["observability"])

log = logging.getLogger(__name__)


# Rate limit: 10 requests/minute for observability endpoints
observability_rate_limit = create_rate_limiter(
    endpoint="observability",
    max_requests=10,
    window_seconds=60,
)


class JobStatsResponse(BaseModel):
    total_jobs: int
    queued: int
    running: int
    completed: int
    failed: int
    avg_duration_sec: Optional[float]
    total_files_indexed: int
    total_symbols_indexed: int
    total_chunks_embedded: int


class BenchmarkStatusResponse(BaseModel):
    retrieval_benchmark_exists: bool
    risk_eval_exists: bool
    last_run: Optional[str] = None


@router.get("/jobs/stats", response_model=JobStatsResponse)
def get_job_stats(
    repo_id: Optional[UUID] = Query(default=None, description="Filter by repo"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(observability_rate_limit),
) -> JobStatsResponse:
    """Get aggregated job statistics."""

    query = db.query(AnalysisJob)
    if repo_id:
        query = query.filter(AnalysisJob.repo_id == repo_id)

    jobs = query.all()

    if not jobs:
        return JobStatsResponse(
            total_jobs=0,
            queued=0,
            running=0,
            completed=0,
            failed=0,
            avg_duration_sec=None,
            total_files_indexed=0,
            total_symbols_indexed=0,
            total_chunks_embedded=0,
        )

    total = len(jobs)
    queued = sum(1 for j in jobs if j.status == "queued")
    running = sum(1 for j in jobs if j.status == "running")
    completed = sum(1 for j in jobs if j.status == "completed")
    failed = sum(1 for j in jobs if j.status == "failed")

    # Average duration for completed jobs
    durations = [
        (j.finished_at - j.started_at).total_seconds()
        for j in jobs
        if j.status == "completed" and j.started_at and j.finished_at
    ]
    avg_duration = sum(durations) / len(durations) if durations else None

    total_files = sum(j.files_indexed or 0 for j in jobs)
    total_symbols = sum(j.symbols_indexed or 0 for j in jobs)
    total_chunks = sum(j.chunks_indexed or 0 for j in jobs)

    return JobStatsResponse(
        total_jobs=total,
        queued=queued,
        running=running,
        completed=completed,
        failed=failed,
        avg_duration_sec=avg_duration,
        total_files_indexed=total_files,
        total_symbols_indexed=total_symbols,
        total_chunks_embedded=total_chunks,
    )


@router.get("/benchmarks/status", response_model=BenchmarkStatusResponse)
def get_benchmark_status(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(observability_rate_limit),
) -> BenchmarkStatusResponse:
    """Check if benchmark files exist and when they were last run."""
    from pathlib import Path

    retrieval_path = Path("benchmarks/retrieval_questions.json")
    risk_path = Path("app/benchmarks/evaluation.json")

    last_run = None
    if risk_path.exists():
        last_run = datetime.fromtimestamp(risk_path.stat().st_mtime).isoformat()

    return BenchmarkStatusResponse(
        retrieval_benchmark_exists=retrieval_path.exists(),
        risk_eval_exists=risk_path.exists(),
        last_run=last_run,
    )


# --- Cost Tracking Endpoints ---


class CostSummaryResponse(BaseModel):
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_latency_ms: float
    by_model: Optional[Dict] = None


@router.get("/costs/summary", response_model=CostSummaryResponse)
def get_cost_summary(
    repo_id: Optional[UUID] = Query(default=None, description="Filter by repo"),
    current_user: CurrentUser = Depends(observability_rate_limit),
) -> CostSummaryResponse:
    """Get LLM cost summary, filtered to the caller's own usage."""
    tracker = get_cost_tracker()
    summary = tracker.get_summary(repo_id=repo_id, user_id=str(current_user.id))
    by_model = tracker.get_by_model(user_id=str(current_user.id))

    return CostSummaryResponse(
        total_calls=summary["total_calls"],
        total_input_tokens=summary["total_input_tokens"],
        total_output_tokens=summary["total_output_tokens"],
        total_cost_usd=summary["total_cost_usd"],
        avg_latency_ms=summary["avg_latency_ms"],
        by_model=by_model,
    )
