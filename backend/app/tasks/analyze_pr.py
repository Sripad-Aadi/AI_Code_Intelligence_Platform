"""Step 13/14 — Celery task for PR analysis.

Runs the full PR analysis pipeline asynchronously:
fetch diff → map to symbols → 1-hop impact → test files → risk scores.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.session import db_session
from app.models.repository import ProjectRepository
from app.pr_analysis.chain import run_pr_analysis_sync
from app.worker import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True, name="pr_analysis.analyze_pr", max_retries=3, default_retry_delay=60
)
def analyze_pr_task(
    self,
    repo_id: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    head_sha: str,
    base_sha: str,
    github_delivery_id: str,
) -> dict:
    """
    Analyze a pull request for impact and risk.

    Args:
        repo_id: ProjectRepository UUID
        pr_number: GitHub PR number
        pr_title: PR title
        pr_body: PR description
        head_sha: Head commit SHA
        base_sha: Base commit SHA
        github_delivery_id: GitHub webhook delivery ID (for idempotency)

    Returns:
        Dict with analysis result or error
    """
    repo_uuid = UUID(repo_id)

    with db_session() as db:
        # Get repository and verify it exists
        repo = db.get(ProjectRepository, repo_uuid)
        if not repo:
            return {"ok": False, "error": f"Repository {repo_id} not found"}

        # Get the user's GitHub access token
        from app.models.project import Project
        from app.models.user import User

        project = db.get(Project, repo.project_id)
        if not project:
            return {"ok": False, "error": f"Project for repo {repo_id} not found"}

        owner = db.get(User, project.owner_id)
        if not owner or not owner.github_access_token:
            return {"ok": False, "error": "GitHub not linked for project owner"}

        try:
            # Run the analysis
            result = run_pr_analysis_sync(
                db=db,
                repo_id=repo_uuid,
                pr_number=pr_number,
                pr_title=pr_title,
                pr_body=pr_body,
                head_sha=head_sha,
                base_sha=base_sha,
                access_token=owner.github_access_token,
            )

            log.info(
                "PR analysis completed for %s PR #%d", repo.github_full_name, pr_number
            )

            return {
                "ok": True,
                "repo_id": repo_id,
                "pr_number": pr_number,
                "github_delivery_id": github_delivery_id,
                "result": result.model_dump(),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:  # noqa: BLE001
            log.exception(
                "PR analysis failed for %s PR #%d", repo.github_full_name, pr_number
            )
            # Retry on transient errors
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)

            return {
                "ok": False,
                "error": str(exc),
                "repo_id": repo_id,
                "pr_number": pr_number,
                "github_delivery_id": github_delivery_id,
            }
