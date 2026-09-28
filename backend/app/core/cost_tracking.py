"""Cost tracking for LLM API calls (Step 19).

Tracks token usage, estimated costs, and latency for LLM requests.
"""

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

log = logging.getLogger(__name__)

# Model pricing (USD per 1M tokens) - approximate as of 2024
MODEL_PRICING = {
    # Groq models
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
    """In-memory cost tracker with optional DB persistence."""

    def __init__(self):
        self._records: list[LLMUsage] = []

    def record(self, usage: LLMUsage) -> None:
        """Record an LLM usage event."""
        self._records.append(usage)
        log.info(
            "LLM usage: model=%s provider=%s tokens=%d/%d cost=$%.6f latency=%dms",
            usage.model,
            usage.provider,
            usage.input_tokens,
            usage.output_tokens,
            usage.estimated_cost_usd,
            usage.latency_ms,
        )

    def get_summary(self, repo_id: Optional[UUID] = None) -> Dict:
        """Get cost summary, optionally filtered by repo."""
        records = self._records
        if repo_id:
            records = [r for r in self._records if r.repo_id == repo_id]

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

    def get_by_model(self) -> Dict:
        """Get usage grouped by model."""
        result: Dict[str, Dict] = {}
        for r in self._records:
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
    """Calculate estimated cost for a model call."""
    pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


async def track_llm_call(
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    repo_id: Optional[UUID] = None,
) -> LLMUsage:
    """Record an LLM API call and return the usage record."""
    cost = calculate_cost(model, input_tokens, output_tokens)
    usage = LLMUsage(
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        estimated_cost_usd=cost,
        request_id=request_id,
        user_id=user_id,
        repo_id=repo_id,
    )
    _tracker.record(usage)
    return usage


@asynccontextmanager
async def track_llm_latency(
    model: str,
    provider: str,
    request_id: Optional[str] = None,
):
    """Context manager to track LLM call latency."""
    start = time.perf_counter()
    try:
        yield
    finally:
        _latency_ms = int((time.perf_counter() - start) * 1000)
        # Note: tokens would need to be captured from the actual response
        # This is a placeholder for the context manager pattern
        pass
