"""Celery task: ingest one cloned repository (Step 4).

Walks the repo's clone on disk, applies the Step-4 filters, detects languages
by extension, and persists a summary on the analysis_jobs row. The API's
polling endpoint reads that row so the frontend has visible progress.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db.session import db_session
from app.ingestion.filters import iter_source_files
from app.ingestion.language_detect import detect_language
from app.models.job import JOB_COMPLETED, JOB_FAILED, JOB_RUNNING, AnalysisJob
from app.models.repository import ProjectRepository
from app.worker import celery_app


def _clone_dir(repo: ProjectRepository) -> Path:
    """Mirror of the attach path layout: CLONE_ROOT_DIR/<project>/<owner>__<name>."""
    return (
        Path(settings.CLONE_ROOT_DIR)
        / str(repo.project_id)
        / f"{repo.github_owner}__{repo.github_name}"
    )


@celery_app.task(bind=True, name="ingestion.ingest_repo")
def ingest_repo(self, job_id: str) -> dict:
    """Apply filters + language detection to a repo clone and finalize the job."""
    now = datetime.now(timezone.utc)
    with db_session() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return {"ok": False, "error": f"job {job_id} not found"}

        job.status = JOB_RUNNING
        job.started_at = now
        try:
            repo = db.get(ProjectRepository, job.repo_id)
            if repo is None:
                raise ValueError(f"repository row for job {job_id} not found")

            clone_dir = _clone_dir(repo)
            if not clone_dir.is_dir():
                raise FileNotFoundError(
                    f"clone not found at {clone_dir} — attach the repository first"
                )

            # Raw count of every file entry in the tree (includes ignored files).
            files_scanned = sum(len(files) for _, _, files in os.walk(clone_dir))

            languages: dict[str, int] = {}
            files_indexed = 0
            for file_path in iter_source_files(clone_dir):
                files_indexed += 1
                lang = detect_language(file_path.relative_to(clone_dir))
                languages[lang] = languages.get(lang, 0) + 1

            job.files_scanned = files_scanned
            job.files_indexed = files_indexed
            job.languages = languages or None
            job.status = JOB_COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            return {
                "ok": True,
                "files_scanned": files_scanned,
                "files_indexed": files_indexed,
                "languages": languages,
            }
        except Exception as exc:  # noqa: BLE001 — persist any failure on the job
            job.status = JOB_FAILED
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            return {"ok": False, "error": str(exc)}
