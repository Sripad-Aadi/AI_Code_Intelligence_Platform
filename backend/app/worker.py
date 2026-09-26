"""Celery application — broker is Upstash Redis, workers run locally (no Docker).

Run a worker on Windows with the solo pool (Windows has no os.fork, so the
default prefork pool refuses to start):

    celery -A app.worker worker --pool=solo --loglevel=info
"""

from celery import Celery

from app.config import settings


def _broker_url() -> str | None:
    """Resolve the Celery broker URL without ever printing .env contents.

    Priority order:
    1. Explicit CELERY_BROKER_URL (the Upstash *Redis* endpoint works here:
       `rediss://default:<token>@<region>.upstash.io:6379`).
    2. REDIS_URL, when it already is a redis:// or rediss:// URL.
    3. Derive it from the Upstash REST URL + UPSTASH_TOKEN — Upstash uses the
       REST token as the Redis password (user `default`), and the REST host is
       the same host as the Redis endpoint.
    """
    if settings.CELERY_BROKER_URL:
        return settings.CELERY_BROKER_URL
    url = settings.REDIS_URL
    if url.startswith(("redis://", "rediss://")):
        return url
    if url.startswith("https://") and settings.UPSTASH_TOKEN:
        host = url[len("https://") :].split("/", 1)[0]
        return f"rediss://default:{settings.UPSTASH_TOKEN}@{host}:6379"
    return None


def _sanitize_broker(url: str | None) -> str | None:
    """redis-py refuses rediss:// broker URLs without an explicit ssl_cert_reqs.

    Upstash serves a valid public cert; CERT_NONE keeps the client from needing
    a matching local CA bundle (e.g. on Windows) while traffic stays TLS.
    """
    if url is None or not url.startswith("rediss://"):
        return url
    if "ssl_cert_reqs=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}ssl_cert_reqs=CERT_NONE"


_broker = _sanitize_broker(_broker_url())

celery_app = Celery(
    "ai_software_intelligence",
    broker=_broker,
    backend=_broker,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

# Make the worker import (and thus register) our task modules.
celery_app.conf.include = ["app.tasks.inject_repo"]
