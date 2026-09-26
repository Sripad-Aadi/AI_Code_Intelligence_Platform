"""User model — thin wrapper around Supabase auth.users.

We don't own the auth table; Supabase does. This model exists only to give us
a local ORM handle for relationships (projects, repositories) without
duplicating auth data.
"""

from sqlalchemy import Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class User(Base):
    """Local shadow of Supabase auth.users.

    We only store the `id` (UUID) and `created_at`. All auth fields (email,
    password hash, etc.) live in Supabase's `auth.users` table.
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("github_id", name="uq_users_github_id"),)

    id = Column(PG_UUID(as_uuid=True), primary_key=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # GitHub OAuth identity (Step 3). The access token is stored plaintext
    # for now; Step 18 adds encryption-at-rest via ENCRYPTION_KEY.
    github_id = Column(String(100), nullable=True)
    github_login = Column(String(255), nullable=True)
    github_access_token = Column(String(512), nullable=True)
