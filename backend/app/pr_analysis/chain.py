"""Step 14 — PR analysis chain.

Combines diff fetch → impact analysis → risk scores into a structured
Pydantic output for the frontend PR dashboard.
"""

import logging
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

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
    risk_level: Optional[str] = None
    risk_probability: Optional[float] = None


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

    # High-level risk summary
    high_risk_symbols: int
    medium_risk_symbols: int
    low_risk_symbols: int


def _impact_to_output(
    repo_id: UUID,
    pr_number: int,
    pr_title: str,
    changed_files: List[ChangedFile],
    impact: ImpactResult,
) -> PRAnalysisResult:
    """Convert ImpactResult to structured API output."""
    changed_symbols_out = []
    high = medium = low = 0

    for s in impact.changed_symbols:
        risk = impact.risk_scores.get(str(s.symbol_id), {})
        level = risk.get("risk_level")
        prob = risk.get("probability")

        if level == "high":
            high += 1
        elif level == "medium":
            medium += 1
        elif level == "low":
            low += 1

        changed_symbols_out.append(
            ChangedSymbolOut(
                symbol_id=str(s.symbol_id),
                file_path=s.file_path,
                symbol_name=s.symbol_name,
                symbol_kind=s.symbol_kind,
                start_line=s.start_line,
                end_line=s.end_line,
                changed_lines=s.changed_lines,
                risk_level=level,
                risk_probability=prob,
            )
        )

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
        high_risk_symbols=high,
        medium_risk_symbols=medium,
        low_risk_symbols=low,
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
            high_risk_symbols=0,
            medium_risk_symbols=0,
            low_risk_symbols=0,
        )

    # Step 2: Impact analysis
    log.info("Running impact analysis for PR #%d", pr_number)
    impact = analyze_pr_impact(db, repo_id, changed_files)

    # Step 3: Convert to output
    return _impact_to_output(repo_id, pr_number, pr_title, changed_files, impact)


def run_pr_analysis_sync(
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
    Synchronous wrapper for Celery task.
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        run_pr_analysis(
            db, repo_id, pr_number, pr_title, pr_body, head_sha, base_sha, access_token
        )
    )
