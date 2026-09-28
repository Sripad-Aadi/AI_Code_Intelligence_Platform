"""Retrieval quality benchmark harness (Step 19).

Runs a fixed set of test questions against indexed repositories
and measures retrieval quality (recall@k, MRR, etc.).
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from app.retrieval.search import search_code
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Default benchmark questions per repository
# These should be customized per repo with known-good answers
DEFAULT_BENCHMARK_FILE = "benchmarks/retrieval_questions.json"


@dataclass
class BenchmarkQuestion:
    """A single benchmark question with expected answer location."""

    question: str
    repo_id: str
    expected_file_path: str  # The file that should contain the answer
    expected_symbol: Optional[str] = None  # Specific function/class if known
    category: str = "general"  # e.g., "auth", "api", "data_model"


@dataclass
class RetrievalResult:
    """Result of a single retrieval query."""

    question: str
    repo_id: str
    hit_rank: Optional[int]  # 1-indexed rank of expected file, None if not found
    hit_score: Optional[float]  # cosine similarity of the expected file's hit
    top_file: Optional[str]  # Top retrieved file path
    latency_ms: float
    expected_file: str


@dataclass
class BenchmarkSummary:
    """Aggregate benchmark metrics."""

    total_questions: int
    answered: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    mrr: float  # Mean Reciprocal Rank
    avg_latency_ms: float


def load_benchmark_questions(path: Optional[str] = None) -> List[BenchmarkQuestion]:
    """Load benchmark questions from JSON file."""
    if path is None:
        path = DEFAULT_BENCHMARK_FILE

    p = Path(path)
    if not p.exists():
        log.warning("Benchmark file not found: %s", path)
        return []

    with open(p, "r") as f:
        data = json.load(f)

    return [BenchmarkQuestion(**q) for q in data]


def save_benchmark_questions(
    questions: List[BenchmarkQuestion], path: Optional[str] = None
) -> None:
    """Save benchmark questions to JSON file."""
    if path is None:
        path = DEFAULT_BENCHMARK_FILE

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w") as f:
        json.dump([asdict(q) for q in questions], f, indent=2)


def run_retrieval_benchmark(
    db: Session,
    questions: List[BenchmarkQuestion],
    k: int = 10,
) -> tuple[List[RetrievalResult], BenchmarkSummary]:
    """
    Run retrieval benchmark against a set of questions.

    Returns individual results and aggregate summary.
    """
    results: List[RetrievalResult] = []
    reciprocals: List[float] = []
    latencies: List[float] = []

    for q in questions:
        repo_uuid = UUID(q.repo_id)

        start = time.perf_counter()
        hits = search_code(db, repo_id=repo_uuid, query=q.question, k=k)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        # Check if expected file appears in results
        hit_rank = None
        hit_score = None
        top_file = hits[0].file_path if hits else None

        for i, hit in enumerate(hits):
            if hit.file_path == q.expected_file_path:
                hit_rank = i + 1  # 1-indexed
                # `search_code` attaches the pgvector cosine distance to each
                # row; similarity is 1 - distance. The old expression compared
                # the row's embedding against *itself*, which always scored 1.0.
                hit_score = (
                    1.0 - hit.cosine_distance
                    if hasattr(hit, "cosine_distance")
                    else None
                )
                break

        if hit_rank:
            reciprocals.append(1.0 / hit_rank)
        else:
            reciprocals.append(0.0)

        results.append(
            RetrievalResult(
                question=q.question,
                repo_id=q.repo_id,
                hit_rank=hit_rank,
                hit_score=hit_score,
                top_file=top_file,
                latency_ms=latency_ms,
                expected_file=q.expected_file_path,
            )
        )

        log.info(
            "Benchmark: %s -> rank=%s, top=%s, latency=%.1fms",
            q.question[:60],
            hit_rank,
            top_file,
            latency_ms,
        )

    # Compute summary
    total = len(questions)
    answered = sum(1 for r in results if r.hit_rank is not None)

    def recall_at(k_val: int) -> float:
        return (
            sum(1 for r in results if r.hit_rank and r.hit_rank <= k_val) / total
            if total > 0
            else 0.0
        )

    summary = BenchmarkSummary(
        total_questions=total,
        answered=answered,
        recall_at_1=recall_at(1),
        recall_at_3=recall_at(3),
        recall_at_5=recall_at(5),
        recall_at_10=recall_at(10),
        mrr=sum(reciprocals) / len(reciprocals) if reciprocals else 0.0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
    )

    return results, summary


def create_sample_benchmark() -> List[BenchmarkQuestion]:
    """Create a sample benchmark file template."""
    return [
        BenchmarkQuestion(
            question="How does authentication work?",
            repo_id="REPLACE_WITH_REPO_UUID",
            expected_file_path="src/auth/middleware.ts",
            expected_symbol="authMiddleware",
            category="auth",
        ),
        BenchmarkQuestion(
            question="What does the user API endpoint do?",
            repo_id="REPLACE_WITH_REPO_UUID",
            expected_file_path="src/api/routes/user.ts",
            expected_symbol="getUserProfile",
            category="api",
        ),
        BenchmarkQuestion(
            question="How are database models defined?",
            repo_id="REPLACE_WITH_REPO_UUID",
            expected_file_path="src/models/user.py",
            expected_symbol="User",
            category="data_model",
        ),
    ]


if __name__ == "__main__":
    # Generate sample benchmark file
    sample = create_sample_benchmark()
    save_benchmark_questions(sample)
    print(f"Created sample benchmark at {DEFAULT_BENCHMARK_FILE}")
