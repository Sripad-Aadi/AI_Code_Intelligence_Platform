"""Engineered risk features (Step 10).

The six features the plan specifies, in a fixed order that is also baked
into ``risk_eval.py`` ("scale the last 6 columns") and the artifact metadata,
so it must never change without a model-version bump:

1. ``complexity`` — cyclomatic complexity: radon for Python, a branch-keyword
   approximation for every other language (documented, not hidden).
2. ``loc`` — symbol span lines (end - start + 1).
3. ``fan_in`` — files importing this symbol's file (Step 5 import edges).
4. ``fan_out`` — files this symbol's file imports.
5. ``has_test`` — 0/1 filename heuristic for a matching test file.
6. ``churn`` — commits touching the file (0 when git history is unavailable;
   shallow clones usually yield 1).

Fan-in/out are file-level (the Step 5 graph has no call edges — call-graph
tracing is deferred to V3), shared by every symbol in the file. That is an
approximation, and the metadata says so.
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models.code_embedding import CodeEmbedding
from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.repository import ProjectRepository
from app.models.symbol import Symbol

log = logging.getLogger(__name__)

FEATURE_NAMES = ["complexity", "loc", "fan_in", "fan_out", "has_test", "churn"]
N_ENGINEERED = len(FEATURE_NAMES)

# Branch keywords for the non-Python complexity approximation. Deliberately
# coarse: this is the plan's "AST-depth approximation", not a parser.
_BRANCH_RE = re.compile(
    r"\b(if|elif|else if|for|while|except|catch|case|when|switch|until)\b"
    r"|&&|\|\||\?\.",
)


def clone_dir_for(clone_root: Path, project_id: UUID, owner: str, name: str) -> Path:
    """Clone directory for one attached repo — pure path math, unit-tested.

    Layout is ``CLONE_ROOT_DIR/<project_id>/<owner>__<name>`` (see the attach
    endpoint): scoped by project so re-attaching elsewhere cannot collide.
    """
    return clone_root / str(project_id) / f"{owner}__{name}"


def repo_clone_root(db: Session, repo_id: UUID) -> Optional[Path]:
    """Clone directory for this repository, or None if it was never cloned."""
    repo = db.get(ProjectRepository, repo_id)
    if repo is None or not repo.github_owner or not repo.github_name:
        return None
    return clone_dir_for(
        Path(settings.CLONE_ROOT_DIR),
        repo.project_id,
        repo.github_owner,
        repo.github_name,
    )


def python_complexity_by_block(source: str) -> List[Tuple[str, int, int]]:
    """Radon complexity per top-level block: (name, lineno, complexity)."""
    import radon.complexity

    blocks = []
    for block in radon.complexity.cc_visit(source):
        blocks.append((block.name, block.lineno, block.complexity))
    return blocks


def approx_complexity(text: str) -> int:
    """Branch-keyword complexity for non-Python code (minimum 1)."""
    return 1 + len(_BRANCH_RE.findall(text or ""))


def symbol_text(
    db: Session, repo_id: UUID, file_row: SourceFile, symbol: Symbol
) -> Optional[str]:
    """Verbatim source of a symbol span: clone slice first, chunk fallback."""
    root = repo_clone_root(db, repo_id)
    if root is not None:
        candidate = root / file_row.path
        try:
            resolved = candidate.resolve()
            if resolved.is_relative_to(root.resolve()) and resolved.is_file():
                lines = resolved.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                span = lines[symbol.start_line - 1 : symbol.end_line]
                if span:
                    return "\n".join(span)
        except OSError as exc:
            log.warning("could not read %s: %s", file_row.path, exc)
    chunk = (
        db.query(CodeEmbedding)
        .filter(
            CodeEmbedding.repo_id == repo_id,
            CodeEmbedding.file_path == file_row.path,
            CodeEmbedding.symbol_name == symbol.name,
        )
        .first()
    )
    return chunk.content if chunk is not None else None


def file_fan(db: Session, repo_id: UUID) -> Tuple[Dict, Dict]:
    """File-level fan-in / fan-out keyed by file id, from import edges."""
    fan_in: Dict = {}
    fan_out: Dict = {}
    rows = (
        db.query(CodeEdge.source_id, CodeEdge.target_id)
        .filter(
            CodeEdge.repo_id == repo_id,
            CodeEdge.edge_type == "imports",
            CodeEdge.source_kind == "file",
        )
        .all()
    )
    files = {
        row[0]
        for row in (db.query(SourceFile.id).filter(SourceFile.repo_id == repo_id).all())
    }
    for file_id in files:
        fan_in[file_id] = 0
        fan_out[file_id] = 0
    for source_id, target_id in rows:
        if source_id in fan_out:
            fan_out[source_id] += 1
        if target_id in fan_in:
            fan_in[target_id] += 1
    return fan_in, fan_out


def _normalized_stem(filename: str) -> str:
    """Lowercased stem with test affixes and extension stripped."""
    stem = Path(filename).name.lower()
    stem = re.sub(r"\.(py|js|jsx|ts|tsx|java|go|rb|php)$", "", stem)
    stem = re.sub(r"^(test_|test-)", "", stem)
    stem = re.sub(r"(_test|-test|\.test|\.spec|_spec|-spec)$", "", stem)
    return stem


def collect_test_paths(file_paths: List[str]) -> Set[str]:
    """Subset of repo paths that look like test files (pure heuristic)."""
    tests = set()
    for path in file_paths:
        lowered = path.lower()
        name = Path(path).name.lower()
        if (
            "/test/" in lowered
            or "/tests/" in lowered
            or "/__tests__/" in lowered
            or name.startswith("test_")
            or name.startswith("test-")
            or ".test." in name
            or ".spec." in name
            or name.endswith("_test.py")
        ):
            tests.add(path)
    return tests


def has_matching_test(file_path: str, test_paths: Set[str]) -> bool:
    """Filename-heuristic test match for one module (Step 10's rule)."""
    stem = _normalized_stem(Path(file_path).name)
    if not stem:
        return False
    for test_path in test_paths:
        if _normalized_stem(Path(test_path).name) == stem:
            return True
    return False


def file_churn(clone_root: Optional[Path], repo_relative: str) -> int:
    """Commits touching a file, or 0 when git history is unavailable."""
    if clone_root is None or not (clone_root / ".git").exists():
        return 0
    try:
        proc = subprocess.run(
            ["git", "-C", str(clone_root), "log", "--oneline", "--", repo_relative],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def features_for_symbol(
    db: Session,
    repo_id: UUID,
    file_row: SourceFile,
    symbol: Symbol,
    text: Optional[str],
    fan_in: int,
    fan_out: int,
    has_test: bool,
    churn: int,
) -> Dict[str, float]:
    """Assemble the six features; complexity is language-dependent."""
    loc = max(1, symbol.end_line - symbol.start_line + 1)
    complexity: float = 1.0
    if file_row.language == "Python" and text:
        try:
            blocks = python_complexity_by_block(text)
            if blocks:
                # The span may hold one function: take the matching block,
                # else the most complex one found inside it.
                match = [b for b in blocks if b[0] == symbol.name]
                complexity = float((match or blocks)[0][2])
            else:
                complexity = float(approx_complexity(text))
        except Exception as exc:  # radon must never break featurization
            log.warning("radon failed for %s: %s", symbol.name, exc)
            complexity = float(approx_complexity(text or ""))
    elif text:
        complexity = float(approx_complexity(text))
    return {
        "complexity": complexity,
        "loc": float(loc),
        "fan_in": float(fan_in),
        "fan_out": float(fan_out),
        "has_test": 1.0 if has_test else 0.0,
        "churn": float(churn),
    }


def as_vector(features: Dict[str, float]) -> List[float]:
    """Feature dict → fixed-order vector (the trained column order)."""
    return [float(features[name]) for name in FEATURE_NAMES]
