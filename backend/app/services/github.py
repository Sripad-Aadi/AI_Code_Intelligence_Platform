"""GitHub OAuth + repo access helpers (Step 3).

Thin wrappers around the GitHub OAuth and REST APIs using httpx.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.config import settings

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"

_api_headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def build_authorize_url(state: str) -> str:
    """Build the GitHub OAuth authorize URL for the configured app."""
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": settings.GITHUB_SCOPE,
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """Exchange an OAuth authorization code for an access token.

    Returns the full JSON payload (access_token, scope, token_type, ...).
    """
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            GITHUB_ACCESS_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    if "access_token" not in payload:
        raise RuntimeError(f"GitHub token exchange failed: {payload}")
    return payload


def fetch_github_user(access_token: str) -> Dict[str, Any]:
    """Fetch the authenticated GitHub user (GET /user)."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/user",
            headers={**_api_headers, "Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def list_user_repos(access_token: str) -> List[Dict[str, Any]]:
    """List repositories the user can access (owner + collaborator).

    Returns a slim projection of GitHub's /user/repos response.
    """
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/user/repos",
            headers={**_api_headers, "Authorization": f"Bearer {access_token}"},
            params={
                "affiliation": "owner,collaborator",
                "per_page": 100,
                "sort": "updated",
            },
        )
        resp.raise_for_status()
        repos: List[Dict[str, Any]] = resp.json()
    return [
        {
            "id": str(r["id"]),
            "full_name": r["full_name"],
            "owner": r["owner"]["login"],
            "name": r["name"],
            "default_branch": r.get("default_branch"),
            "private": r.get("private", False),
            "html_url": r.get("html_url"),
        }
        for r in repos
    ]


def get_repo(access_token: str, full_name: str) -> Dict[str, Any]:
    """Fetch a single repository (GET /repos/{owner}/{repo})."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{full_name}",
            headers={**_api_headers, "Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        r = resp.json()
    return {
        "id": str(r["id"]),
        "full_name": r["full_name"],
        "owner": r["owner"]["login"],
        "name": r["name"],
        "default_branch": r.get("default_branch"),
        "private": r.get("private", False),
        "html_url": r.get("html_url"),
        "clone_url": r.get("clone_url"),
    }


def get_branch_default_sha(
    access_token: str, full_name: str, branch: str
) -> Optional[str]:
    """Return the HEAD sha for a branch, or None if it can't be resolved."""
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{GITHUB_API_BASE}/repos/{full_name}/branches/{branch}",
                headers={**_api_headers, "Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()["commit"]["sha"]
    except (httpx.HTTPStatusError, KeyError):
        return None
