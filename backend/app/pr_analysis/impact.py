"""Step 14 — PR impact analysis.

Maps changed line ranges to Step 5 symbols, walks the import graph
one hop out to find potentially affected files, and retrieves
related test files via filename heuristic.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.symbol import Symbol
from app.pr_analysis.diff import ChangedFile, get_all_changed_ranges

log = logging.getLogger(__name__)


@dataclass
class AffectedSymbol:
    """A symbol that was directly changed in the PR."""

    symbol_id: UUID
    file_id: UUID
    file_path: str
    symbol_name: str
    symbol_kind: str
    start_line: int
    end_line: int
    changed_lines: List[int]  # Specific lines within the symbol that changed


@dataclass
class ImpactResult:
    """Complete impact analysis result for a PR."""

    # Directly changed symbols
    changed_symbols: List[AffectedSymbol]

    # Files potentially affected (1-hop from changed symbols via imports)
    affected_files: List[Dict]  # {file_path, reason, via_symbol}

    # Test files that should be run (heuristic)
    test_files: List[str]

    # Risk scores for changed symbols (if risk model available)
    risk_scores: Dict[str, Dict]  # symbol_id -> {level, probability}


def _symbol_intersects_range(
    symbol: Symbol,
    ranges: List[Tuple[int, int]],
) -> List[int]:
    """
    Check if a symbol's span intersects any changed range.

    Returns list of specific line numbers within the symbol that were changed.
    """
    changed = []
    for start, end in ranges:
        # Symbol range: [symbol.start_line, symbol.end_line]
        # Changed range: [start, end]
        overlap_start = max(symbol.start_line, start)
        overlap_end = min(symbol.end_line, end)
        if overlap_start <= overlap_end:
            changed.extend(range(overlap_start, overlap_end + 1))
    return sorted(set(changed))


def find_changed_symbols(
    db: Session,
    repo_id: UUID,
    changed_ranges: Dict[str, List[Tuple[int, int]]],
) -> List[AffectedSymbol]:
    """
    Find all symbols whose spans intersect the changed line ranges.

    For each file with changes, query its symbols and check for overlap.
    """
    affected: List[AffectedSymbol] = []

    for file_path, ranges in changed_ranges.items():
        # Get the SourceFile row
        file_row = (
            db.query(SourceFile)
            .filter(
                SourceFile.repo_id == repo_id,
                SourceFile.path == file_path,
            )
            .first()
        )
        if not file_row:
            log.debug("File not in index: %s", file_path)
            continue

        # Get all symbols in this file
        symbols = db.query(Symbol).filter(Symbol.file_id == file_row.id).all()

        for sym in symbols:
            changed_lines = _symbol_intersects_range(sym, ranges)
            if changed_lines:
                affected.append(
                    AffectedSymbol(
                        symbol_id=sym.id,
                        file_id=file_row.id,
                        file_path=file_path,
                        symbol_name=sym.name,
                        symbol_kind=sym.kind,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        changed_lines=changed_lines,
                    )
                )

    log.info(
        "Found %d changed symbols across %d files", len(affected), len(changed_ranges)
    )
    return affected


def find_affected_files_one_hop(
    db: Session,
    repo_id: UUID,
    changed_symbols: List[AffectedSymbol],
) -> List[Dict]:
    """
    Walk the import graph ONE HOP from changed symbols/files.

    Returns files that import the changed files (fan-in) — these are
    potentially affected because they depend on changed code.
    """
    if not changed_symbols:
        return []

    # Get unique file_ids of changed symbols
    changed_file_ids = {s.file_id for s in changed_symbols}

    # Find files that import these files (fan-in via file->file imports edges)

    incoming = (
        db.query(CodeEdge.source_id, CodeEdge.target_id)
        .filter(
            CodeEdge.repo_id == repo_id,
            CodeEdge.edge_type == "imports",
            CodeEdge.source_kind == "file",
            CodeEdge.target_id.in_(changed_file_ids),
        )
        .all()
    )

    if not incoming:
        return []

    # Get source file paths
    source_file_ids = [row.source_id for row in incoming]
    source_files = (
        db.query(SourceFile.id, SourceFile.path)
        .filter(
            SourceFile.id.in_(source_file_ids),
        )
        .all()
    )
    file_id_to_path = {f.id: f.path for f in source_files}

    # Build result
    affected_files = []
    for source_id, target_id in incoming:
        source_path = file_id_to_path.get(source_id)
        target_file = (
            db.query(SourceFile.path).filter(SourceFile.id == target_id).scalar()
        )
        if source_path and target_file:
            affected_files.append(
                {
                    "file_path": source_path,
                    "reason": "imports_changed_file",
                    "via_symbol": target_file,
                }
            )

    # Deduplicate by file_path
    seen = set()
    unique = []
    for af in affected_files:
        if af["file_path"] not in seen:
            seen.add(af["file_path"])
            unique.append(af)

    log.info("Found %d potentially affected files (1-hop fan-in)", len(unique))
    return unique


TEST_FILE_PATTERNS = [
    "test_*.py",
    "*_test.py",
    "*.test.ts",
    "*.test.tsx",
    "*.test.js",
    "*.test.jsx",
    "*_test.go",
    "*Test.java",
    "*Test.cs",
    "*_test.rs",
    "test_*.rs",
]


def find_related_test_files(
    db: Session,
    repo_id: UUID,
    changed_symbols: List[AffectedSymbol],
    affected_files: List[Dict],
) -> List[str]:
    """
    Heuristic: find test files related to changed/affected files.

    Strategies:
    1. Same directory, matching test_* or *_test pattern
    2. Parallel tests/ directory
    3. Files importing the changed files (already in affected_files)
    """
    from pathlib import Path

    # Collect all relevant file paths
    relevant_paths: Set[str] = set()
    for s in changed_symbols:
        relevant_paths.add(s.file_path)
    for af in affected_files:
        relevant_paths.add(af["file_path"])

    test_files: Set[str] = set()

    for path in relevant_paths:
        p = Path(path)
        parent = p.parent
        stem = p.stem

        # Strategy 1: Same directory, test patterns
        for pattern in TEST_FILE_PATTERNS:
            # Convert glob to SQL LIKE
            pass  # We'll query DB directly

        # Strategy 2: DB query for test files in same directory
        # Match files in same directory with test-like names
        dir_path = str(parent)
        if dir_path == ".":
            dir_path = ""

        # Query for test files in same directory
        test_rows = (
            db.query(SourceFile.path)
            .filter(
                SourceFile.repo_id == repo_id,
                SourceFile.path.like(f"{dir_path}/test_%")
                if dir_path
                else SourceFile.path.like("test_%"),
            )
            .all()
        )
        for row in test_rows:
            test_files.add(row.path)

        test_rows = (
            db.query(SourceFile.path)
            .filter(
                SourceFile.repo_id == repo_id,
                SourceFile.path.like(f"{dir_path}/%_test")
                if dir_path
                else SourceFile.path.like("%_test"),
            )
            .all()
        )
        for row in test_rows:
            test_files.add(row.path)

        # Strategy 3: Parallel tests/ directory
        tests_dir = f"tests/{dir_path}" if dir_path else "tests"
        test_rows = (
            db.query(SourceFile.path)
            .filter(
                SourceFile.repo_id == repo_id,
                SourceFile.path.like(f"{tests_dir}/%"),
            )
            .all()
        )
        for row in test_rows:
            test_files.add(row.path)

        # Strategy 4: Test files matching the stem
        test_rows = (
            db.query(SourceFile.path)
            .filter(
                SourceFile.repo_id == repo_id,
                SourceFile.path.like(f"%{stem}%test%"),
            )
            .all()
        )
        for row in test_rows:
            test_files.add(row.path)

    log.info("Found %d related test files", len(test_files))
    return sorted(test_files)


def get_risk_scores_for_symbols(
    db: Session,
    repo_id: UUID,
    symbol_ids: List[UUID],
) -> Dict[str, Dict]:
    """
    Fetch risk findings for the given symbols.
    """
    from app.models.risk_finding import RiskFinding

    if not symbol_ids:
        return {}

    rows = (
        db.query(RiskFinding)
        .filter(
            RiskFinding.repo_id == repo_id,
            RiskFinding.symbol_id.in_(symbol_ids),
        )
        .all()
    )

    return {
        str(r.symbol_id): {
            "risk_level": r.risk_level,
            "probability": r.probability,
            "model_version": r.model_version,
        }
        for r in rows
    }


def analyze_pr_impact(
    db: Session,
    repo_id: UUID,
    changed_files: List[ChangedFile],
) -> ImpactResult:
    """
    Full PR impact analysis pipeline.

    1. Map changed line ranges to symbols
    2. Walk 1-hop fan-in to find affected files
    3. Find related test files
    4. Attach risk scores if available
    """
    # Step 1: Get changed line ranges per file
    changed_ranges = get_all_changed_ranges(changed_files)

    # Step 2: Find directly changed symbols
    changed_symbols = find_changed_symbols(db, repo_id, changed_ranges)

    # Step 3: Find affected files (1-hop fan-in)
    affected_files = find_affected_files_one_hop(db, repo_id, changed_symbols)

    # Step 3: Find related test files
    test_files = find_related_test_files(db, repo_id, changed_symbols, affected_files)

    # Step 4: Get risk scores for changed symbols
    symbol_ids = [s.symbol_id for s in changed_symbols]
    risk_scores = get_risk_scores_for_symbols(db, repo_id, symbol_ids)

    return ImpactResult(
        changed_symbols=changed_symbols,
        affected_files=affected_files,
        test_files=test_files,
        risk_scores=risk_scores,
    )
