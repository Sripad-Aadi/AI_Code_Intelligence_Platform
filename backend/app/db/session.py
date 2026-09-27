"""Database engine and session management."""

from contextlib import contextmanager
from typing import Generator

from pgvector.psycopg2 import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)


@event.listens_for(engine, "connect")
def _register_vector_types(dbapi_connection, _record) -> None:
    """Teach psycopg2 about the `vector` type (Step 7).

    Without this, binding a list of floats to a `Vector` column has no adapter
    and the value goes out as an untyped parameter. pgvector ships implicit
    text<->vector casts, so the INSERT would often survive anyway — but
    reading a row back would hand us a raw string instead of a vector.
    """
    register_vector(dbapi_connection)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for standalone database operations (e.g., Celery tasks)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
