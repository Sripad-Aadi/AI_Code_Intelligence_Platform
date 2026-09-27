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
import os
import threading
import time
from typing import List, Sequence

from app.config import settings

log = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


def _configure_threads():
    """Pin the CPU thread count before torch initialises its thread pools.

    Defaults to leaving torch alone: measured on the i5-1235U that this step was
    tuned on, thread counts 8/10/12 were all within run-to-run noise of each
    other and of torch's default, so pinning bought nothing. The knob exists for
    other hardware, not as a fix for this machine.

    `OMP_NUM_THREADS` is consumed by the OpenMP runtime when it initialises,
    which happens as a side effect of importing torch. So the env vars are
    exported *before* the first `import torch` in this process — which is why
    this is called ahead of the import rather than after it, and why it lives
    in the lazy `get_model` path instead of at module scope. The explicit
    `torch.set_num_threads` afterwards covers the case where something else
    already imported torch (e.g. a test harness or another task).

    Returns the pin that was applied, or None if the setting is unset.
    """
    n = settings.EMBEDDING_TORCH_THREADS
    if n is None:
        return None
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = str(n)
    import torch

    torch.set_num_threads(n)
    return n


def get_model():
    """Return the cached SentenceTransformer, loading it on first use."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Must run before `import torch` (see _configure_threads), so
                # it cannot be hoisted above the imports below. No-op unless
                # EMBEDDING_TORCH_THREADS is set: on the machine this was tuned
                # on, torch's own default beat every explicit thread count.
                pinned = _configure_threads()

                # Imported here, not at module scope: the API process should
                # boot (and `EMBEDDING_ENABLED=false` should work) without
                # torch installed.
                import torch
                from sentence_transformers import SentenceTransformer

                log.info(
                    "loading embedding model %s on cpu (max_seq_length=%d, "
                    "torch_threads=%d, pinned=%s)",
                    settings.EMBEDDING_MODEL,
                    settings.EMBEDDING_MAX_SEQ_LENGTH,
                    torch.get_num_threads(),
                    pinned if pinned is not None else "unset (torch default)",
                )
                started = time.perf_counter()
                model = SentenceTransformer(
                    settings.EMBEDDING_MODEL,
                    trust_remote_code=True,
                    device="cpu",
                )
                model.max_seq_length = settings.EMBEDDING_MAX_SEQ_LENGTH
                _model = model
                # Load cost and encode cost are very different numbers (tens of
                # seconds vs. steady-state per-batch), so they are logged
                # separately: the first job in a worker pays the load, every
                # later one does not.
                log.info(
                    "embedding model ready in %.1fs (%s); encode starts now",
                    time.perf_counter() - started,
                    time.strftime("%H:%M:%S"),
                )
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
