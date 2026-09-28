"""Application configuration via environment variables."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (Supabase Postgres)
    DATABASE_URL: str = Field(..., description="PostgreSQL connection string")

    # Redis / Upstash (Celery broker)
    REDIS_URL: str = Field(..., description="Upstash Redis REST URL")
    UPSTASH_TOKEN: str = Field(..., description="Upstash Redis token")
    CELERY_BROKER_URL: Optional[str] = Field(
        default=None,
        description=(
            "Redis URL for the Celery broker. Optional — when unset, the "
            "worker derives rediss:// from REDIS_URL + UPSTASH_TOKEN."
        ),
    )

    # Supabase Auth
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_SERVICE_KEY: str = Field(..., description="Supabase service role key")

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = Field(..., description="GitHub OAuth app client ID")
    GITHUB_CLIENT_SECRET: str = Field(..., description="GitHub OAuth app client secret")
    GITHUB_REDIRECT_URI: str = Field(
        default="http://localhost:8000/auth/github/callback",
        description="GitHub OAuth redirect URI",
    )
    GITHUB_SCOPE: str = Field(
        default="repo", description="GitHub OAuth scope(s) — repo = list + clone"
    )

    # Frontend origin — the GitHub OAuth callback redirects browsers here so
    # the popup never sits on a code-bearing URL (Step 6)
    FRONTEND_URL: str = Field(
        default="http://localhost:5173",
        description="Frontend origin the GitHub OAuth callback redirects to",
    )

    # Where shallow clones land on the server's own disk (Step 3)
    CLONE_ROOT_DIR: str = Field(
        default="./.clones", description="Dir for shallow git clones of repos"
    )

    # Code embeddings (Step 7) — CPU-only sentence-transformers model
    EMBEDDING_ENABLED: bool = Field(
        default=True,
        description=(
            "Set false to run Steps 4-5 ingestion without downloading/loading "
            "the embedding model (structure is still indexed)."
        ),
    )
    EMBEDDING_MODEL: str = Field(
        default="jinaai/jina-embeddings-v2-base-code",
        description="sentence-transformers model id (768-dim, 512 trained ctx)",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=16, description="Chunks per forward pass (plan: 16-32 on CPU)"
    )
    EMBEDDING_MAX_SEQ_LENGTH: int = Field(
        default=512,
        description=(
            "Token cap per chunk. This is the model's *trained* context (the "
            "8192 figure is an extrapolation) and it is also the single "
            "biggest cost lever: measured on an i5-1235U, embedding runs at a "
            "flat ~191 tok/s of padded input, and the chunk length "
            "distribution is long-tailed (median 152 tokens, p90 645, max "
            "3458), so the one batch of longest chunks dominated total ingest "
            "time. Capping at 512 leaves 69 of 77 demo chunks untouched and "
            "shrinks the worst batch ~6.8x. Truncation affects only the "
            "vector — `content` is still stored verbatim."
        ),
    )
    EMBEDDING_TORCH_THREADS: Optional[int] = Field(
        default=None,
        description=(
            "torch CPU threads for the embed pass. Unset = torch's default, "
            "which measured FASTER than any pin on this machine (see AGENTS.md "
            "for the table), so leave it alone unless you are tuning a "
            "different CPU. When set, app/embeddings/jina.py exports "
            "OMP_NUM_THREADS/MKL_NUM_THREADS before importing torch (OpenMP "
            "reads them at init) and then calls torch.set_num_threads()."
        ),
    )

    # LLM Provider
    LLM_PROVIDER: str = Field(default="groq", description="LLM provider (groq|gemini)")
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API key")

    # Webhooks
    WEBHOOK_SECRET: Optional[str] = Field(
        default=None, description="GitHub webhook secret"
    )
    WEBHOOK_URL: Optional[str] = Field(
        default=None,
        description="Public webhook URL (e.g., ngrok URL) for GitHub webhooks",
    )

    # Encryption (for stored tokens)
    ENCRYPTION_KEY: Optional[str] = Field(
        default=None, description="Fernet encryption key"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
