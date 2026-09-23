"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import projects_router, repos_router


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


# API routers
app.include_router(projects_router)
app.include_router(repos_router)

# Placeholders for future steps (Step 3+)
# from app.api import auth, ingestion, chat, findings, pull_requests, search, webhooks
# app.include_router(auth.router)
# app.include_router(ingestion.router)
# app.include_router(chat.router)
# app.include_router(findings.router)
# app.include_router(pull_requests.router)
# app.include_router(search.router)
# app.include_router(webhooks.router)
