"""GitHub OAuth routes (Step 3).

Flow (no frontend yet — driven from Swagger/curl until Step 6):

1. Caller passes their Supabase JWT as `state`:
   GET /auth/github/login?state=<supabase-jwt>
   → returns a 307 redirect to GitHub's authorize URL (state echoed back).
2. User authorizes; GitHub redirects to /auth/github/callback?code=...&state=...
3. Callback exchanges the code for an access token, captures the GitHub
   identity, and stores it against the Supabase user identified by `state`.
4. GitHub-scoped endpoints (GET /user/repos, repo attach) then use the stored
   token via normal Supabase-JWT auth.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, decode_supabase_token, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import github

router = APIRouter(prefix="/auth", tags=["auth"])


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
    db: Session = Depends(get_db),
):
    """Exchange the OAuth code, then store the GitHub identity on the user."""
    try:
        token_payload = await decode_supabase_token(state)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state token: {e}",
        )
    user_id = token_payload.sub

    try:
        token_data = github.exchange_code_for_token(code)
        gh_user = github.fetch_github_user(token_data["access_token"])
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id)
    user.github_id = gh_user["id"]
    user.github_login = gh_user["login"]
    user.github_access_token = token_data["access_token"]
    db.add(user)
    db.commit()
    db.refresh(user)

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
