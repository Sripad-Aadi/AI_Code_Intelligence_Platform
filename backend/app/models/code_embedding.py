"""CodeEmbedding model — one embedded chunk of a repository (Step 7).

A row is a *retrievable unit*: the verbatim source span of a chunk plus the
metadata needed to cite it as evidence later (file, symbol, exact line
range). Step 8 searches these with pgvector's cosine operator; Step 9 hands
`content` + `file_path` + lines to the chat LLM as sources.

The plan's column list is (id, repo_id, file_path, symbol_name, start_line,
end_line, embedding vector(768), content); `file_id`, `language` and
`symbol_kind` are additions because the plan's focus for this step is
"get the metadata right on every vector row" — the FK keeps rows in sync
with `files` (ON DELETE CASCADE drops chunks when a repo is re-indexed) and
`language` lets Step 8 filter without a join.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base

# jinaai/jina-embeddings-v2-base-code emits 768-d vectors. Kept as a constant
# because it is baked into the column type (vector(768)) and the HNSW index.
EMBEDDING_DIM = 768


class CodeEmbedding(Base):
    """One chunk of code/text with its 768-d embedding.

    `start_line`/`end_line` are 1-based and inclusive and always delimit
    `content` exactly — the invariant Step 9 relies on to quote real lines.
    `symbol_name`/`symbol_kind` are NULL for chunks that came from a file
    with no parseable structure (markdown/config), which are split into
    paragraph or heading sections instead.
    """

    __tablename__ = "code_embeddings"
    __table_args__ = (
        Index("ix_code_embeddings_repo_id", "repo_id"),
        Index("ix_code_embeddings_repo_file", "repo_id", "file_path"),
        Index("ix_code_embeddings_file_id", "file_id"),
        # Step 7 plan: HNSW cosine index, created by the Alembic migration
        # (reproducible, unlike pasting it into the Supabase SQL editor).
        Index(
            "ix_code_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=True,
    )
    file_path = Column(Text, nullable=False)  # repo-relative, posix separators
    language = Column(String(50), nullable=True)  # detect_language() label
    symbol_kind = Column(String(20), nullable=True)  # function|class|method|route
    symbol_name = Column(String(512), nullable=True)  # NULL for text chunks
    start_line = Column(Integer, nullable=False)  # 1-based, inclusive
    end_line = Column(Integer, nullable=False)  # 1-based, inclusive
    content = Column(Text, nullable=False)  # verbatim source span
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
