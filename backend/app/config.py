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

    # LLM Provider
    LLM_PROVIDER: str = Field(default="groq", description="LLM provider (groq|gemini)")
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API key")

    # Webhooks
    WEBHOOK_SECRET: Optional[str] = Field(
        default=None, description="GitHub webhook secret"
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
