"""GitHub OAuth + repo access helpers (Step 3).

Thin wrappers around the GitHub OAuth and REST APIs using httpx.
"""

from typing import Any, Dict, List
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


def get_pull_request(
    access_token: str, owner: str, repo_name: str, number: int
) -> Dict[str, Any]:
    """Fetch one PR (GET /repos/{owner}/{repo}/pulls/{n}) — slim projection."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/pulls/{number}",
            headers={**_api_headers, "Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        pr = resp.json()
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    return {
        "number": pr["number"],
        "title": pr.get("title") or "",
        "body": pr.get("body") or "",
        "state": pr.get("state"),
        "head_sha": (head.get("sha") or ""),
        "base_sha": (base.get("sha") or ""),
        "head_ref": head.get("ref"),
        "base_ref": base.get("ref"),
        "html_url": pr.get("html_url"),
    }


def list_pull_requests(
    access_token: str, owner: str, repo_name: str, state: str = "open"
) -> List[Dict[str, Any]]:
    """List PRs (GET /repos/{owner}/{repo}/pulls) — slim projection."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/pulls",
            headers={**_api_headers, "Authorization": f"Bearer {access_token}"},
            params={
                "state": state,
                "per_page": 30,
                "sort": "updated",
                "direction": "desc",
            },
        )
        resp.raise_for_status()
        pulls: List[Dict[str, Any]] = resp.json()
    return [
        {
            "number": pr["number"],
            "title": pr.get("title") or "",
            "state": pr.get("state"),
            "head_ref": (pr.get("head") or {}).get("ref"),
            "base_ref": (pr.get("base") or {}).get("ref"),
            "html_url": pr.get("html_url"),
        }
        for pr in pulls
    ]
