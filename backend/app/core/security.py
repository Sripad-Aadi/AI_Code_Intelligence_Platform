"""Supabase JWT authentication dependency."""

from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    from app.models.repository import ProjectRepository

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db

# Supabase uses RS256 with a JWKS endpoint
# JWKS URL format: https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """Decoded JWT payload from Supabase."""

    sub: str  # user UUID
    email: Optional[str] = None
    role: str = "authenticated"
    aud: str = "authenticated"
    exp: int


class CurrentUser(BaseModel):
    """Authenticated user context for request handlers."""

    id: UUID
    email: Optional[str] = None


_jwks_cache: Optional[dict] = None


async def get_jwks() -> dict:
    """Fetch and cache Supabase JWKS public keys."""
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(SUPABASE_JWKS_URL)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def decode_supabase_token(token: str) -> TokenPayload:
    """Validate a Supabase JWT using the JWKS public keys."""
    jwks = await get_jwks()
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if not kid:
        raise JWTError("Token missing 'kid' header")

    key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if not key:
        # Cache might be stale; force refresh once
        global _jwks_cache
        _jwks_cache = None
        jwks = await get_jwks()
        key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if not key:
            raise JWTError(f"Key '{kid}' not found in JWKS")

    # Supabase can sign with either RS256 (RSA JWKs) or ES256 (EC JWKs).
    # python-jose can build the key directly from the JWK dict for both.
    alg = unverified_header.get("alg")
    if alg not in ("RS256", "ES256"):
        raise JWTError(f"Unsupported token algorithm '{alg}'")

    payload = jwt.decode(
        token,
        key,
        algorithms=[alg],
        audience="authenticated",
        options={"verify_aud": True},
    )
    return TokenPayload(**payload)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """FastAPI dependency: extract and validate Supabase JWT, return CurrentUser.

    Raises 401 if token is missing, invalid, or expired.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = await decode_supabase_token(credentials.credentials)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = UUID(payload.sub)

    # Ensure a local shadow user row exists (upsert)
    from app.models.user import User

    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id)
        db.add(user)
        db.commit()

    return CurrentUser(id=user_id, email=payload.email)


def require_project_owner(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Dependency that verifies the current user owns the given project.

    Use as: `project_owner: CurrentUser = Depends(require_project_owner)`
    in route handlers that need ownership check.
    """
    from app.models.project import Project

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this project",
        )
    return current_user


def get_owned_repo(
    repo_id: UUID, current_user: CurrentUser, db: Session
) -> "ProjectRepository":
    """Return the repo row if it belongs to one of the user's projects.

    Shared helper used by ingestion, analysis, search, chat, and PR routers
    to enforce that a repository belongs to the caller's project.
    """
    from app.models.project import Project
    from app.models.repository import ProjectRepository

    repo = db.get(ProjectRepository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    project = db.get(Project, repo.project_id)
    if project is None or project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to access this repository"
        )
    return repo
