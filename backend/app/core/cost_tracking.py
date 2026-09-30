"""Cost tracking for LLM API calls (Step 19).

Tracks token usage, estimated costs, and latency for LLM requests.
Persisted to a JSON file so records survive server restarts.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import UUID

log = logging.getLogger(__name__)

COST_FILE = Path(__file__).resolve().parent.parent / "cost_records.json"

# Model pricing (USD per 1M tokens), the provider's list price. A free-tier
# Groq key bills $0 regardless — this is what the same call would cost paid.
MODEL_PRICING = {
    # Groq models (rates from console.groq.com/docs/models)
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "qwen/qwen3.8-27b": {"input": 0.80, "output": 4.00},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "gemma-7b-it": {"input": 0.07, "output": 0.07},
    "gemma2-9b-it": {"input": 0.10, "output": 0.10},
    # Google models
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    # OpenAI models (for reference)
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


@dataclass
class LLMUsage:
    """Record of a single LLM API call."""

    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost_usd: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    repo_id: Optional[UUID] = None


class CostTracker:
    """File-persisted cost tracker — records survive server restarts."""

    def __init__(self):
        self._records: list[LLMUsage] = []
        self._load()

    def _load(self) -> None:
        """Load records from the JSON file."""
        if not COST_FILE.exists():
            return
        try:
            with open(COST_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for row in data:
                self._records.append(
                    LLMUsage(
                        model=row["model"],
                        provider=row["provider"],
                        input_tokens=row["input_tokens"],
                        output_tokens=row["output_tokens"],
                        latency_ms=row["latency_ms"],
                        estimated_cost_usd=row["estimated_cost_usd"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        request_id=row.get("request_id"),
                        user_id=row.get("user_id"),
                        repo_id=UUID(row["repo_id"]) if row.get("repo_id") else None,
                    )
                )
        except Exception:
            log.exception("could not load cost records from %s", COST_FILE)

    def _save(self) -> None:
        """Persist records to the JSON file."""
        try:
            with open(COST_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "model": r.model,
                            "provider": r.provider,
                            "input_tokens": r.input_tokens,
                            "output_tokens": r.output_tokens,
                            "latency_ms": r.latency_ms,
                            "estimated_cost_usd": r.estimated_cost_usd,
                            "timestamp": r.timestamp.isoformat(),
                            "request_id": r.request_id,
                            "user_id": r.user_id,
                            "repo_id": str(r.repo_id) if r.repo_id else None,
                        }
                        for r in self._records
                    ],
                    f,
                    indent=2,
                )
        except Exception:
            log.exception("could not save cost records to %s", COST_FILE)

    def record(self, usage: LLMUsage) -> None:
        """Record an LLM usage event."""
        self._records.append(usage)
        self._save()
        log.info(
            "LLM usage: model=%s provider=%s tokens=%d/%d cost=$%.6f latency=%dms",
            usage.model,
            usage.provider,
            usage.input_tokens,
            usage.output_tokens,
            usage.estimated_cost_usd,
            usage.latency_ms,
        )

    def get_summary(
        self,
        repo_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
    ) -> Dict:
        """Get cost summary, optionally filtered by repo and/or user."""
        records = self._records
        if repo_id:
            records = [r for r in records if r.repo_id == repo_id]
        if user_id:
            records = [r for r in records if r.user_id == user_id]

        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.estimated_cost_usd for r in records)
        total_calls = len(records)
        avg_latency = (
            sum(r.latency_ms for r in records) / total_calls if total_calls > 0 else 0
        )

        return {
            "total_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_cost, 6),
            "avg_latency_ms": round(avg_latency, 1),
        }

    def get_by_model(self, user_id: Optional[str] = None) -> Dict:
        """Get usage grouped by model, optionally filtered by user."""
        result: Dict[str, Dict] = {}
        for r in self._records:
            if user_id and r.user_id != user_id:
                continue
            if r.model not in result:
                result[r.model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            result[r.model]["calls"] += 1
            result[r.model]["input_tokens"] += r.input_tokens
            result[r.model]["output_tokens"] += r.output_tokens
            result[r.model]["cost_usd"] += r.estimated_cost_usd
        return result


# Global tracker instance
_tracker = CostTracker()


def get_cost_tracker() -> CostTracker:
    return _tracker


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated cost of one call in USD.

    An unknown model would otherwise be a *silent* zero, so it is logged —
    a cost summary stuck at $0.00 should be diagnosable from the log.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        log.warning("no pricing entry for model %r; cost recorded as 0", model)
        pricing = {"input": 0.0, "output": 0.0}
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)
