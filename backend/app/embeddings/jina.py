"""Step 7 — embedding generation with jinaai/jina-embeddings-v2-base-code.

CPU-only via sentence-transformers, loaded lazily and cached per process:
the Celery worker embeds every repo it ingests, so paying the load (and the
first-run download from the HuggingFace Hub) per job would be wasteful.

The model is 161M params and emits **768-d, mean-pooled, L2-normalised**
vectors. Normalisation is why pgvector's cosine operator is the right
comparison downstream: for unit vectors cosine distance is `1 - dot(a, b)`.

`trust_remote_code=True` is required — the Hub repo ships a custom
`JinaBertForMaskedLM` architecture behind an `auto_map`, so plain
`AutoModel`/`SentenceTransformer` loading fails without it. That does mean
executing code fetched from the Hub, which is acceptable here because the
model id is pinned in `requirements.txt`/`.env` and the weights are
Apache-2.0; set `HF_HUB_OFFLINE=1` to forbid the download entirely.
"""

import logging
import threading
from typing import List, Sequence

from app.config import settings

log = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


def get_model():
    """Return the cached SentenceTransformer, loading it on first use."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Imported here, not at module scope: the API process should
                # boot (and `EMBEDDING_ENABLED=false` should work) without
                # torch installed.
                from sentence_transformers import SentenceTransformer

                log.info(
                    "loading embedding model %s on cpu (max_seq_length=%d)",
                    settings.EMBEDDING_MODEL,
                    settings.EMBEDDING_MAX_SEQ_LENGTH,
                )
                model = SentenceTransformer(
                    settings.EMBEDDING_MODEL,
                    trust_remote_code=True,
                    device="cpu",
                )
                model.max_seq_length = settings.EMBEDDING_MAX_SEQ_LENGTH
                _model = model
    return _model


def embed_passages(texts: Sequence[str]) -> List[List[float]]:
    """Embed repository chunks (the indexed side). Batched, CPU, normalised.

    No task prompt is prepended: the model card for this code-tuned variant
    documents plain `encode()` and lists no task prefixes (unlike the v2
    English cards). `embed_query` is the matching query-side entry point for
    Step 8, kept separate so asymmetric prompts can be added in one place if
    retrieval quality later calls for it.
    """
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        list(texts),
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vec.tolist() for vec in vectors]


def embed_query(text: str) -> List[float]:
    """Embed a search query (Step 8). Same model/space as `embed_passages`."""
    return embed_passages([text])[0]
