"""Ingestion API — trigger repo ingestion jobs and poll their status (Step 4).

The ingest endpoint only enqueues a Celery task and returns immediately
(202); all of the heavy walking happens in the worker process. Clients poll
`GET /jobs/{job_id}` while that runs.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.job import JOB_FAILED, JOB_QUEUED, AnalysisJob
from app.models.repository import ProjectRepository
from app.schemas.job import AnalysisJobRead

router = APIRouter(tags=["ingestion"])


def _get_owned_repo(
    repo_id: UUID, current_user: CurrentUser, db: Session
) -> ProjectRepository:
    """Return the repo row if it belongs to one of the user's projects."""
    from app.models.project import Project

    repo = db.get(ProjectRepository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    project = db.get(Project, repo.project_id)
    if project is None or project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to access this repository"
        )
    return repo


@router.post(
    "/repos/{repo_id}/ingest",
    response_model=AnalysisJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_ingestion(
    repo_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalysisJob:
    """Create a queued analysis job and dispatch it to the Celery worker."""
    _get_owned_repo(repo_id, current_user, db)

    job = AnalysisJob(repo_id=repo_id, status=JOB_QUEUED)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Imported here so the API can boot even if the broker is down; the task
    # itself pulls `app.worker` for the shared Celery app.
    from app.tasks.inject_repo import ingest_repo

    try:
        ingest_repo.delay(str(job.id))
    except Exception as e:  # broker unreachable / misconfigured
        job.status = JOB_FAILED
        job.error = f"Failed to enqueue: {e}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Could not enqueue job: {e}. Is the Celery broker configured? "
                "Set CELERY_BROKER_URL in backend/.env."
            ),
        )

    return job


@router.get("/jobs/{job_id}", response_model=AnalysisJobRead)
def get_job_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalysisJob:
    """Poll a single job's status (the frontend calls this while indexing)."""
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    _get_owned_repo(job.repo_id, current_user, db)
    return job


@router.get("/repos/{repo_id}/jobs", response_model=List[AnalysisJobRead])
def list_repo_jobs(
    repo_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AnalysisJob]:
    """List recent ingestion jobs for a repository (newest first)."""
    _get_owned_repo(repo_id, current_user, db)
    return (
        db.query(AnalysisJob)
        .filter(AnalysisJob.repo_id == repo_id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(limit)
        .all()
    )
