"""Rate limiting for expensive endpoints (Step 18).

Uses in-memory token bucket (per-process). For production multi-instance,
replace with Redis-backed rate limiter.
"""

import logging
import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, status

from app.core.security import CurrentUser, get_current_user

log = logging.getLogger(__name__)

# In-memory store: {user_id: {endpoint: [timestamps]}}
_request_logs: dict[str, dict[str, list[float]]] = defaultdict(
    lambda: defaultdict(list)
)


def _clean_old_entries(user_id: str, endpoint: str, window_seconds: int) -> None:
    """Remove timestamps older than the window."""
    now = time.time()
    cutoff = now - window_seconds
    logs = _request_logs[user_id][endpoint]
    # Keep only recent entries
    _request_logs[user_id][endpoint] = [ts for ts in logs if ts > cutoff]


def check_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """
    Check if request is within rate limit.

    Returns: (allowed, remaining_requests)
    """
    _clean_old_entries(user_id, endpoint, window_seconds)

    current_count = len(_request_logs[user_id][endpoint])
    if current_count >= max_requests:
        return False, 0

    _request_logs[user_id][endpoint].append(time.time())
    return True, max_requests - current_count - 1


# Chat endpoint: 20 requests/minute per user
async def chat_rate_limit(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Rate limit: 20 requests/minute for chat endpoint."""
    allowed, remaining = check_rate_limit(
        user_id=str(current_user.id),
        endpoint="chat",
        max_requests=20,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Chat rate limit exceeded (20 req/min). Please wait.",
            headers={"Retry-After": "60"},
        )
    request.state.rate_limit_remaining = remaining
    return current_user


# PR analysis endpoint: 10 requests/minute per user (heavier than chat:
# GitHub diff fetch + embeddings + one LLM summary per call).
async def pr_analysis_rate_limit(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Rate limit: 10 requests/minute for the PR analysis endpoint."""
    allowed, remaining = check_rate_limit(
        user_id=str(current_user.id),
        endpoint="pr_analysis",
        max_requests=10,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="PR analysis rate limit exceeded (10 req/min). Please wait.",
            headers={"Retry-After": "60"},
        )
    request.state.rate_limit_remaining = remaining
    return current_user


# Generic dependency for custom limits
def create_rate_limiter(
    endpoint: str,
    max_requests: int,
    window_seconds: int,
):
    """Factory for custom rate limit dependencies."""

    async def rate_limiter(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        allowed, remaining = check_rate_limit(
            user_id=str(current_user.id),
            endpoint=endpoint,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if not allowed:
            window = f"{max_requests} req/{window_seconds}s"
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {endpoint} ({window})",
                headers={"Retry-After": str(window_seconds)},
            )
        request.state.rate_limit_remaining = remaining
        return current_user

    return rate_limiter
