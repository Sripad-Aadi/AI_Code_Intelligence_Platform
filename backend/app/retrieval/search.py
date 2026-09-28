"""Step 8 — semantic retrieval over the Step 7 ``code_embeddings`` table.

The query side of the vector index: embed the question with the *same* jina
model that embedded the chunks (``embed_query`` and ``embed_passages`` share
one process-cached model, one sequence length and one L2 normalisation, so the
two live in the same vector space), then rank with pgvector's cosine operator
``<=>`` filtered by ``repo_id`` and optionally ``language``/``file_path``.

Distance, not similarity: ``<=>`` returns ``1 - cos(a, b)``, so 0.0 is a
perfect match and 1.0 is orthogonal. Results come back nearest-first and each
row carries its own ``cosine_distance`` so callers can report a real score
without re-running the query.

Called from two places: ``app/api/search.py`` (the Search page) and
``app/benchmarks/retrieval_benchmark.py`` (recall@k / MRR on fixed questions).
Both pass a live SQLAlchemy session, so this module stays synchronous —
FastAPI runs sync endpoints in its threadpool and the benchmark is a script.
"""

import logging
import time
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings.jina import embed_query
from app.models.code_embedding import CodeEmbedding

log = logging.getLogger(__name__)

# Step 8: "Return the top 8-10 candidate chunks per query." 10 is the default;
# the ceiling is 50 because the Search page exposes k as a control and the
# benchmark runs at k=10 by default.
DEFAULT_K = 10
MAX_K = 50


def search_code(
    db: Session,
    query: str,
    repo_id: Optional[UUID] = None,
    repo_ids: Optional[Sequence[UUID]] = None,
    k: int = DEFAULT_K,
    language: Optional[str] = None,
    file_path: Optional[str] = None,
) -> List[CodeEmbedding]:
    """Return the top-k chunks for ``query``, nearest first.

    Args:
        db: live session (owned by the caller — this never commits).
        query: natural-language or keyword question.
        repo_id: restrict to one repository (the common case).
        repo_ids: restrict to a set of repositories. When *both* are given,
            ``repo_id`` wins — callers use them for different endpoints.
        k: how many chunks to return, clamped to ``MAX_K``.
        language: exact ``detect_language()`` label.
        file_path: exact repo-relative path, for "search inside this file".

    Returns:
        ORM ``CodeEmbedding`` rows, each with a ``cosine_distance`` float
        attached. Empty list when nothing matches (or the query is blank).
    """
    if not query or not query.strip():
        return []

    k = max(1, min(int(k), MAX_K))

    # Loading happens inside the query so a search never pays for torch unless
    # it actually runs; the model is cached per process afterwards.
    started = time.perf_counter()
    query_vector = embed_query(query)
    embed_ms = (time.perf_counter() - started) * 1000

    # The vector goes in as a plain Python list, not as "[0.1, ...]" text.
    # pgvector's SQLAlchemy bind processor (VECTOR.bind_processor →
    # Vector._to_db) only accepts list/ndarray/Vector: a *string* raises
    # `ValueError: expected list or ndarray` at execute time. `_to_db` does
    # the text serialisation itself once it is handed a list.
    distance = CodeEmbedding.embedding.cosine_distance(query_vector)

    stmt = select(CodeEmbedding, distance.label("cosine_distance"))
    if repo_id is not None:
        stmt = stmt.where(CodeEmbedding.repo_id == repo_id)
    elif repo_ids is not None:
        stmt = stmt.where(CodeEmbedding.repo_id.in_(list(repo_ids)))
    if language:
        stmt = stmt.where(CodeEmbedding.language == language)
    if file_path:
        stmt = stmt.where(CodeEmbedding.file_path == file_path)
    stmt = stmt.order_by(distance).limit(k)

    rows = db.execute(stmt).all()

    # Attach the distance to the ORM instance (a plain attribute, not a mapped
    # column) so callers can score a hit without a second round-trip.
    hits: List[CodeEmbedding] = []
    for row, dist in rows:
        row.cosine_distance = float(dist)
        hits.append(row)

    log.info(
        "search: q=%r repo=%s hits=%d embed=%.0fms total_rows_considered=%d",
        query[:60],
        repo_id or "all",
        len(hits),
        embed_ms,
        len(rows),
    )
    return hits
