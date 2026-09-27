"""add code_embeddings table and analysis_jobs.chunks_indexed (step 7)

Revision ID: d7c86d75d7b7
Revises: a6dac032b9b5
Create Date: 2026-09-27 14:58:51.483845

"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7c86d75d7b7"
down_revision: Union[str, Sequence[str], None] = "a6dac032b9b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# jinaai/jina-embeddings-v2-base-code emits 768 dims.
EMBEDDING_DIM = 768


def upgrade() -> None:
    """Upgrade schema."""
    # pgvector is enabled in the Supabase dashboard (one-click toggle). The
    # IF NOT EXISTS keeps this migration self-sufficient on a fresh database
    # without failing on a project that already has it.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "code_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("symbol_kind", sa.String(length=20), nullable=True),
        sa.Column("symbol_name", sa.String(length=512), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(EMBEDDING_DIM),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["repo_id"], ["project_repositories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_code_embeddings_repo_id", "code_embeddings", ["repo_id"], unique=False
    )
    op.create_index(
        "ix_code_embeddings_repo_file",
        "code_embeddings",
        ["repo_id", "file_path"],
        unique=False,
    )
    op.create_index(
        "ix_code_embeddings_file_id", "code_embeddings", ["file_id"], unique=False
    )
    # Cosine HNSW index, per the Step 7 plan. Created by the migration rather
    # than pasted into the Supabase SQL editor so it is reproducible and can be
    # dropped by `alembic downgrade`. vector_cosine_ops matches the L2-
    # normalised vectors the embedding model produces.
    op.create_index(
        "ix_code_embeddings_embedding_hnsw",
        "code_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    # server_default '0' so existing analysis_jobs rows survive the NOT NULL.
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "chunks_indexed",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Step 7: chunks embedded into code_embeddings",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("analysis_jobs", "chunks_indexed")
    op.drop_index(
        "ix_code_embeddings_embedding_hnsw",
        table_name="code_embeddings",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_code_embeddings_file_id", table_name="code_embeddings")
    op.drop_index("ix_code_embeddings_repo_file", table_name="code_embeddings")
    op.drop_index("ix_code_embeddings_repo_id", table_name="code_embeddings")
    op.drop_table("code_embeddings")
