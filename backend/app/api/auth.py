"""GitHub OAuth routes (Step 3).

Flow (driven from the Step-6 frontend "Link GitHub" popup, or curl):

1. Caller passes their Supabase JWT as `state`:
   GET /auth/github/login?state=<supabase-jwt>
   → returns a 307 redirect to GitHub's authorize URL (state echoed back).
2. User authorizes; GitHub redirects to /auth/github/callback?code=...&state=...
3. Callback exchanges the code for an access token, captures the GitHub
   identity, and stores it against the Supabase user identified by `state`.
   Browsers are 302-redirected to `{FRONTEND_URL}/linked` (the popup closes
   itself); API clients get the JSON result.
4. GitHub-scoped endpoints (GET /user/repos, repo attach) then use the stored
   token via normal Supabase-JWT auth.
"""

from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import CurrentUser, decode_supabase_token, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import github

router = APIRouter(prefix="/auth", tags=["auth"])


def _oauth_redirect(
    *,
    login: Optional[str] = None,
    error: Optional[str] = None,
) -> RedirectResponse:
    """302 the OAuth popup to the frontend completion page (`/linked`).

    Returning a redirect instead of JSON means the browser never sits on a
    code-bearing callback URL — refreshing that page would resubmit an already
    consumed `code`, and GitHub replies `bad_verification_code`.
    """
    params: dict[str, str] = {}
    if login:
        params["login"] = login
    if error:
        params["error"] = error
    url = f"{settings.FRONTEND_URL}/linked"
    if params:
        url = f"{url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/github/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def github_login(
    state: str,
    db: Session = Depends(get_db),
):
    """Start GitHub OAuth. `state` must be the caller's Supabase JWT.

    It is echoed by GitHub on the callback so the token can be bound to the
    right local user row.
    """
    # Validate the state is a real Supabase JWT before sending the user to GitHub.
    try:
        await decode_supabase_token(state)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"state must be a valid Supabase JWT: {e}",
        )

    url = github.build_authorize_url(state)
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Exchange the OAuth code, then store the GitHub identity on the user.

    Browsers (Accept: text/html) get a 302 to ``/linked`` on the frontend so
    the OAuth popup can close itself cleanly; API clients keep the JSON
    response shape.
    """
    is_browser = "text/html" in request.headers.get("accept", "")

    try:
        token_payload = await decode_supabase_token(state)
    except JWTError as e:
        if is_browser:
            return _oauth_redirect(error=f"Invalid OAuth state: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state token: {e}",
        )
    user_id = token_payload.sub

    try:
        token_data = github.exchange_code_for_token(code)
        gh_user = github.fetch_github_user(token_data["access_token"])
    except RuntimeError as e:
        if is_browser:
            return _oauth_redirect(error=str(e))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id)

    # A GitHub account can only be bound to one `users` row
    # (uq_users_github_id). If it's already bound to a different Supabase
    # account — e.g. the same human signed up twice — unlink the old row so
    # the current caller owns the link and the UPDATE below can't violate
    # the unique constraint (which previously 500'd the callback).
    previous_owner = (
        db.query(User)
        .filter(User.github_id == gh_user["id"], User.id != user_id)
        .first()
    )
    if previous_owner is not None:
        previous_owner.github_id = None
        previous_owner.github_login = None
        previous_owner.github_access_token = None
        db.add(previous_owner)

    user.github_id = gh_user["id"]
    user.github_login = gh_user["login"]
    user.github_access_token = token_data["access_token"]
    db.add(user)
    db.commit()
    db.refresh(user)

    if is_browser:
        return _oauth_redirect(login=gh_user["login"])

    return {
        "status": "ok",
        "user_id": str(user.id),
        "github_id": user.github_id,
        "github_login": user.github_login,
    }


@router.get("/github/status")
async def github_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return whether the caller has linked GitHub (id + login, no secret)."""
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {
        "linked": bool(user.github_access_token),
        "github_id": user.github_id,
        "github_login": user.github_login,
    }
