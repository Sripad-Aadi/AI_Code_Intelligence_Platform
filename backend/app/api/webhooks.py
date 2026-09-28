"""Step 13/16 — GitHub webhooks endpoint.

Subscribes to pull_request events (opened, synchronize) and push events.
Verifies X-Hub-Signature-256 via HMAC before processing.
Enqueues Celery jobs and returns 200 immediately.
"""

import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limit import pr_webhook_rate_limit
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.repository import ProjectRepository
from app.tasks.analyze_pr import analyze_pr_task
from app.tasks.reindex_changed import reindex_changed_files_task

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

log = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """Verify X-Hub-Signature-256 header using HMAC-SHA256."""
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[7:])


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _rate_limit: bool = Depends(pr_webhook_rate_limit),
) -> dict:
    """
    GitHub webhook receiver for pull_request and push events.

    Expected events:
      - pull_request (opened, synchronize, reopened)
      - push (for incremental indexing)
    """
    # Read raw body for signature verification
    body = await request.body()

    # Verify webhook secret
    if not settings.WEBHOOK_SECRET:
        log.warning("WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook secret not configured"
        )

    if not x_hub_signature_256:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-Hub-Signature-256")

    if not _verify_signature(body, x_hub_signature_256, settings.WEBHOOK_SECRET):
        log.warning("Invalid webhook signature from delivery %s", x_github_delivery)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON payload")

    # Handle pull_request events
    if x_github_event == "pull_request":
        action = payload.get("action")
        if action not in ("opened", "synchronize", "reopened"):
            return {"status": "ignored", "action": action}

        repo_data = payload.get("repository", {})
        repo_full_name = repo_data.get("full_name")
        if not repo_full_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing repository info")

        repo = (
            db.query(ProjectRepository)
            .filter(ProjectRepository.github_full_name == repo_full_name)
            .first()
        )
        if not repo:
            log.info("Webhook for untracked repo: %s", repo_full_name)
            return {"status": "ignored", "reason": "repo not tracked"}

        pr_data = payload.get("pull_request", {})
        pr_number = pr_data.get("number")
        pr_title = pr_data.get("title", "")
        pr_body = pr_data.get("body", "")
        head_sha = pr_data.get("head", {}).get("sha")
        base_sha = pr_data.get("base", {}).get("sha")

        if not all([pr_number, head_sha, base_sha]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing PR metadata")

        try:
            analyze_pr_task.delay(
                repo_id=str(repo.id),
                pr_number=pr_number,
                pr_title=pr_title,
                pr_body=pr_body,
                head_sha=head_sha,
                base_sha=base_sha,
                github_delivery_id=x_github_delivery,
            )
        except Exception as e:
            log.exception("Failed to enqueue PR analysis task")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"Failed to queue analysis: {e}"
            )

        return {"status": "queued", "repo_id": str(repo.id), "pr_number": pr_number}

    # Handle push events (Step 16: incremental indexing)
    if x_github_event == "push":
        repo_data = payload.get("repository", {})
        repo_full_name = repo_data.get("full_name")
        if not repo_full_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing repository info")

        repo = (
            db.query(ProjectRepository)
            .filter(ProjectRepository.github_full_name == repo_full_name)
            .first()
        )
        if not repo:
            log.info("Push webhook for untracked repo: %s", repo_full_name)
            return {"status": "ignored", "reason": "repo not tracked"}

        # Extract changed files from push payload
        ref = payload.get("ref", "")
        if not ref.startswith("refs/heads/"):
            return {"status": "ignored", "reason": "not a branch push"}

        branch = ref.replace("refs/heads/", "")
        head_commit = payload.get("head_commit", {})
        head_sha = head_commit.get("id")
        before_sha = payload.get("before")

        # Get list of changed files (added, modified, removed)
        commits = payload.get("commits", [])
        changed_files: list[str] = []
        for commit in commits:
            changed_files.extend(commit.get("added", []))
            changed_files.extend(commit.get("modified", []))
            changed_files.extend(commit.get("removed", []))

        # Deduplicate
        seen = set()
        unique_files = []
        for f in changed_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)

        if not unique_files:
            return {"status": "ignored", "reason": "no file changes"}

        # Enqueue incremental re-index task
        try:
            reindex_changed_files_task.delay(
                repo_id=str(repo.id),
                branch=branch,
                head_sha=head_sha,
                base_sha=before_sha,
                changed_files=unique_files,
                github_delivery_id=x_github_delivery,
            )
        except Exception as e:
            log.exception("Failed to enqueue incremental reindex task")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"Failed to queue reindex: {e}"
            )

        return {
            "status": "queued",
            "repo_id": str(repo.id),
            "branch": branch,
            "files_changed": len(unique_files),
        }

    return {"status": "ignored", "event": x_github_event}


# Admin endpoint to register webhook on a repository (for setup)
@router.post("/github/register/{repo_id}")
async def register_webhook(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Register this app's webhook URL on the GitHub repository.
    Requires admin access to the repo.
    """
    from uuid import UUID

    from app.api.ingestion import _get_owned_repo
    from app.services.github import register_webhook_on_repo

    repo = _get_owned_repo(UUID(repo_id), current_user, db)

    if not settings.WEBHOOK_SECRET:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "WEBHOOK_SECRET not configured in environment",
        )

    webhook_url = f"{settings.FRONTEND_URL.replace('5173', '8000')}/webhooks/github"

    try:
        result = await register_webhook_on_repo(
            access_token=repo.project.owner.github_access_token,  # type: ignore
            owner=repo.github_owner,
            repo_name=repo.github_name,
            webhook_url=webhook_url,
            secret=settings.WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"GitHub API error: {e}")

    return {"status": "registered", "webhook_id": result.get("id")}


# Admin endpoint to list webhooks on a repository
@router.get("/github/list/{repo_id}")
async def list_webhooks(
    repo_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List webhooks registered on the GitHub repository.
    """
    from uuid import UUID

    from app.api.ingestion import _get_owned_repo
    from app.services.github import list_webhooks_on_repo

    repo = _get_owned_repo(UUID(repo_id), current_user, db)

    try:
        hooks = await list_webhooks_on_repo(
            access_token=repo.project.owner.github_access_token,  # type: ignore
            owner=repo.github_owner,
            repo_name=repo.github_name,
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"GitHub API error: {e}")

    return {"webhooks": hooks}


# Admin endpoint to delete a webhook
@router.delete("/github/delete/{repo_id}/{hook_id}")
async def delete_webhook(
    repo_id: str,
    hook_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Delete a webhook from the GitHub repository.
    """
    from uuid import UUID

    from app.api.ingestion import _get_owned_repo
    from app.services.github import delete_webhook_on_repo

    repo = _get_owned_repo(UUID(repo_id), current_user, db)

    try:
        await delete_webhook_on_repo(
            access_token=repo.project.owner.github_access_token,  # type: ignore
            owner=repo.github_owner,
            repo_name=repo.github_name,
            hook_id=hook_id,
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"GitHub API error: {e}")

    return {"status": "deleted", "hook_id": hook_id}
