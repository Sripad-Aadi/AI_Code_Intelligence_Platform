"""API package exports."""

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.ingestion import router as ingestion_router
from app.api.observability import router as observability_router
from app.api.projects import router as projects_router
from app.api.repos import router as repos_router
from app.api.search import router as search_router
from app.api.webhooks import router as webhooks_router

__all__ = [
    "auth_router",
    "projects_router",
    "repos_router",
    "ingestion_router",
    "analysis_router",
    "search_router",
    "observability_router",
    "webhooks_router",
]
