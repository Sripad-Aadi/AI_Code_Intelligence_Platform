"""Step 14 — PR analysis chain.

Combines diff fetch → impact analysis → LLM summary into a
structured Pydantic output for the frontend PR dashboard.

The LLM step is deliberately *not* a tool-calling agent (unlike chat): the
evidence is already assembled deterministically above, so the model gets one
tool-free completion under a JSON contract. That path cannot 400 on
malformed tool calls or loop to force-stop — the two failure modes that
made chat need a fallback. If the provider call fails, the structural
analysis still returns; only the summary degrades.
"""

import json
import logging
import re
import time
from typing import List, Optional
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.agents.chat_chain import _sanitize_answer
from app.config import settings
from app.core.cost_tracking import LLMUsage, calculate_cost, get_cost_tracker
from app.models.repository import ProjectRepository
from app.pr_analysis.diff import ChangedFile, fetch_pr_diff
from app.pr_analysis.impact import ImpactResult, analyze_pr_impact

log = logging.getLogger(__name__)


# Pydantic output models for structured API response
class ChangedSymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol_id: str
    file_path: str
    symbol_name: str
    symbol_kind: str
    start_line: int
    end_line: int
    changed_lines: List[int]


class AffectedFileOut(BaseModel):
    file_path: str
    reason: str
    via_symbol: str


class PRAnalysisResult(BaseModel):
    """Structured output for the PR dashboard."""

    repo_id: str
    pr_number: int
    pr_title: str

    # Summary counts
    files_changed: int
    symbols_changed: int
    affected_files_count: int
    test_files_count: int

    # Detailed data
    changed_symbols: List[ChangedSymbolOut]
    affected_files: List[AffectedFileOut]
    test_files: List[str]

    # LLM impact summary (Step 14 chain output; empty when ungenerated)
    summary: str = ""
    key_risks: List[str] = []


class PRSummary(BaseModel):
    """Structured LLM verdict: what this PR does and what to watch.

    The model answers in JSON under this schema (validated, never parsed
    by hand into the response) so the frontend receives consistent fields
    instead of free text to parse — the plan's requirement.
    """

    summary_markdown: str
    key_risks: List[str] = []


SUMMARY_SYSTEM = """\
You review a pull request from its diff highlights, changed symbols and affected
files. Reply with a single JSON object and nothing else:
{"summary_markdown": "<2-4 sentence overview plus what to review carefully>",
"key_risks": ["<at most 5 short risk bullets>"]}.
Rules: only describe what the evidence shows; cite file paths you were given;
if the evidence is thin, say so instead of inventing impact; keep key_risks
empty when nothing stands out.
"""


def _extract_json(text: str) -> dict:
    """Parse the model's JSON, tolerating fences and stray prose."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start : end + 1])
    return parsed if isinstance(parsed, dict) else {}


def _prompt_context(
    pr_title: str,
    pr_body: str,
    changed_files: List[ChangedFile],
    impact: ImpactResult,
    max_files: int = 20,
) -> str:
    """Bounded evidence text for the summary call (never the full diff)."""
    lines = [f"PR title: {pr_title}", f"PR body: {(pr_body or '')[:800]}"]
    for changed in changed_files[:max_files]:
        hunks = []
        for hunk in changed.hunks[:2]:
            hunks.append("\n".join(hunk.lines[:40]))
        lines.append(f"--- {changed.file_path} ({changed.status})\n" + "\n".join(hunks))
    for symbol in impact.changed_symbols[:30]:
        lines.append(
            f"symbol: {symbol.symbol_kind} {symbol.symbol_name} "
            f"in {symbol.file_path}:{symbol.start_line}-{symbol.end_line}"
        )
    for affected in impact.affected_files[:30]:
        lines.append(
            f"affected: {affected['file_path']} "
            f"({affected['reason']} via {affected['via_symbol']})"
        )
    lines.append(f"tests: {', '.join(impact.test_files[:20]) or '(none found)'}")
    return "\n".join(lines)[:8000]


def summarize_impact(
    repo_id: UUID,
    pr_title: str,
    pr_body: str,
    changed_files: List[ChangedFile],
    impact: ImpactResult,
) -> PRSummary:
    """One tool-free Groq completion over assembled evidence.

    Raises RuntimeError with a clear cause when the key is missing or the
    provider fails — the caller degrades to structural-only output.
    """
    if settings.LLM_PROVIDER.lower() != "groq" or not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured, skipping PR summary")
    llm = ChatGroq(
        model=(settings.LLM_MODEL or "openai/gpt-oss-20b").strip()
        or "openai/gpt-oss-20b",
        groq_api_key=settings.GROQ_API_KEY,
        temperature=0,
        timeout=30,
        max_retries=1,
        disable_streaming=True,
    )
    started = time.perf_counter()
    message = llm.invoke(
        [
            SystemMessage(content=SUMMARY_SYSTEM),
            HumanMessage(
                content=_prompt_context(pr_title, pr_body, changed_files, impact)
                + "\n\nReply with the JSON object only."
            ),
        ]
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    content = message.content if isinstance(message.content, str) else ""
    try:
        parsed = PRSummary(**_extract_json(content))
    except Exception:
        log.warning("PR summary was not valid JSON; keeping raw text")
        parsed = PRSummary(
            summary_markdown=_sanitize_answer(content.strip()),
            key_risks=[],
        )
    meta = getattr(message, "usage_metadata", None) or {}
    try:
        get_cost_tracker().record(
            LLMUsage(
                model=llm.model_name,
                provider=settings.LLM_PROVIDER,
                input_tokens=int(meta.get("input_tokens") or 0),
                output_tokens=int(meta.get("output_tokens") or 0),
                latency_ms=latency_ms,
                estimated_cost_usd=calculate_cost(
                    llm.model_name,
                    int(meta.get("input_tokens") or 0),
                    int(meta.get("output_tokens") or 0),
                ),
                repo_id=repo_id,
            )
        )
    except Exception:
        log.exception("could not record PR summary usage")
    return parsed


def _impact_to_output(
    repo_id: UUID,
    pr_number: int,
    pr_title: str,
    changed_files: List[ChangedFile],
    impact: ImpactResult,
    summary: Optional[PRSummary] = None,
) -> PRAnalysisResult:
    """Convert ImpactResult to structured API output."""
    changed_symbols_out = [
        ChangedSymbolOut(
            symbol_id=str(s.symbol_id),
            file_path=s.file_path,
            symbol_name=s.symbol_name,
            symbol_kind=s.symbol_kind,
            start_line=s.start_line,
            end_line=s.end_line,
            changed_lines=s.changed_lines,
        )
        for s in impact.changed_symbols
    ]

    return PRAnalysisResult(
        repo_id=str(repo_id),
        pr_number=pr_number,
        pr_title=pr_title,
        files_changed=len(changed_files),
        symbols_changed=len(impact.changed_symbols),
        affected_files_count=len(impact.affected_files),
        test_files_count=len(impact.test_files),
        changed_symbols=changed_symbols_out,
        affected_files=[
            AffectedFileOut(
                file_path=af["file_path"],
                reason=af["reason"],
                via_symbol=af["via_symbol"],
            )
            for af in impact.affected_files
        ],
        test_files=impact.test_files,
        summary=summary.summary_markdown if summary is not None else "",
        key_risks=list(summary.key_risks) if summary is not None else [],
    )


async def run_pr_analysis(
    db: Session,
    repo_id: UUID,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    head_sha: str,
    base_sha: str,
    access_token: str,
) -> PRAnalysisResult:
    """
    Full PR analysis pipeline:
    1. Fetch diff from GitHub
    2. Run impact analysis
    3. Return structured result
    """
    # Get repo metadata for GitHub API call
    repo_row = db.get(ProjectRepository, repo_id)
    if not repo_row:
        raise ValueError(f"Repository {repo_id} not found")

    owner = repo_row.github_owner
    repo_name = repo_row.github_name

    # Step 1: Fetch diff
    log.info("Fetching diff for %s/%s PR #%d", owner, repo_name, pr_number)
    changed_files = await fetch_pr_diff(owner, repo_name, pr_number, access_token)

    if not changed_files:
        log.warning("No changed files in PR #%d", pr_number)
        return PRAnalysisResult(
            repo_id=str(repo_id),
            pr_number=pr_number,
            pr_title=pr_title,
            files_changed=0,
            symbols_changed=0,
            affected_files_count=0,
            test_files_count=0,
            changed_symbols=[],
            affected_files=[],
            test_files=[],
            summary="",
            key_risks=[],
        )

    # Step 2: Impact analysis
    log.info("Running impact analysis for PR #%d", pr_number)
    impact = analyze_pr_impact(db, repo_id, changed_files)

    # Step 3: LLM summary over assembled evidence (degrades, never fails)
    summary: Optional[PRSummary] = None
    try:
        summary = summarize_impact(repo_id, pr_title, pr_body, changed_files, impact)
    except Exception as exc:
        log.warning("PR summary skipped (structural output kept): %s", exc)

    # Step 4: Convert to output
    return _impact_to_output(
        repo_id, pr_number, pr_title, changed_files, impact, summary
    )
