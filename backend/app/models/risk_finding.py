"""RiskFinding model — one classifier verdict per symbol (Step 12).

A row is the persisted output of the Step 11 model for one symbol in one
indexed repository: the predicted level, the probability of that level, the
feature values that produced it (auditable without re-running the model),
and the model version that made the call. Re-training deletes a repo's old
rows first, so the table always reflects the latest training run rather
than accumulating stale verdicts under different versions.
"""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base


class RiskFinding(Base):
    """A 3-class risk verdict (low|medium|high) for one code symbol."""

    __tablename__ = "risk_findings"
    __table_args__ = (
        Index("ix_risk_findings_repo_id", "repo_id"),
        Index("ix_risk_findings_symbol_id", "symbol_id"),
        Index("ix_risk_findings_repo_level", "repo_id", "risk_level"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="CASCADE"),
        nullable=False,
    )
    risk_level = Column(String(10), nullable=False)  # low|medium|high
    probability = Column(Float, nullable=False)
    features_json = Column(JSONB, nullable=False, server_default="{}")
    model_version = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
