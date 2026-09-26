"""User model — thin wrapper around Supabase auth.users.

We don't own the auth table; Supabase does. This model exists only to give us
a local ORM handle for relationships (projects, repositories) without
duplicating auth data.
"""

from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class User(Base):
    """Local shadow of Supabase auth.users.

    We only store the `id` (UUID) and `created_at`. All auth fields (email,
    password hash, etc.) live in Supabase's `auth.users` table.
    """

    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
