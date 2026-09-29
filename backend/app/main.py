"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    analysis_router,
    auth_router,
    chat_router,
    ingestion_router,
    observability_router,
    projects_router,
    repos_router,
    search_router,
    webhooks_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm JWKS cache
    from app.core.security import get_jwks

    try:
        await get_jwks()
    except Exception:
        pass  # Non-blocking; first request will fetch
    yield
    # Shutdown: nothing special for now


app = FastAPI(
    title="AI Software Engineering Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for local frontend (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check (no auth)
@app.get("/health")
def health_check():
    return {"status": "ok"}


# API routers. `search_router` is mounted before `repos_router` on purpose:
# its `/repos/search` route must be matched ahead of any `/repos/{repo_id}`
# route, or "search across repos" would be read as a repo id.
app.include_router(auth_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(projects_router)
app.include_router(repos_router)
app.include_router(ingestion_router)
app.include_router(analysis_router)
app.include_router(observability_router)
app.include_router(webhooks_router)

# Not mounted yet — these have no endpoint file (their 0-byte scaffold was
# deleted in the 2026-09-28 cleanup), so implementing Steps 12 and 14 means
# writing them first:
#   app/api/findings.py       (Step 12)
#   app/api/pull_requests.py  (Step 14)
