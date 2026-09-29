"""Repository tools for the Step 9 chat agent.

The plan asks for four thin wrappers over data that already exists —
``search_code`` (Step 8 retrieval), ``get_file`` and ``get_symbol`` (Step 5
files/symbols), ``get_dependencies`` (Step 5 import edges) — and that is all
this module is. No new storage, no new analysis.

Two properties matter more than the tools themselves:

* They are built **per request** and closed over one repo id, so the model
  can never name another repository: no tool accepts a repo id argument, and
  every query filters on the bound ``repo_id``. The router has already
  checked ownership; the tools do not get a chance to disagree.
* ``get_file`` reads paths the *model* supplied, so that path is untrusted
  input. :func:`safe_clone_path` refuses anything that escapes the clone
  root (``../../etc/passwd``, an absolute path, a symlink out) — otherwise a
  prompt could turn "read this file" into "read the server's .env".

Tool output is prompt text, so each result is clipped: one enormous file
must not eat the model's context window.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.orm import Session

from app.config import settings
from app.models.code_embedding import CodeEmbedding
from app.models.edge import CodeEdge
from app.models.file import SourceFile
from app.models.repository import ProjectRepository
from app.models.symbol import Symbol
from app.retrieval.search import search_code
from app.schemas.chat import EvidenceChunk

log = logging.getLogger(__name__)

# Prompt budget: per tool result, and how many chunks the answer may cite.
MAX_TOOL_CHARS = 6000
MAX_EVIDENCE = 8


def safe_clone_path(clone_root: Path, repo_relative: str) -> Optional[Path]:
    """Resolve ``repo_relative`` inside ``clone_root``, else ``None``.

    Pure and dependency-free so it can be unit-tested directly. ``None`` means
    "do not touch this path": empty, absolute, or escaping the clone root.
    """
    if not repo_relative:
        return None
    try:
        root = clone_root.resolve()
    except OSError:
        return None
    # `resolve()` collapses `..` and follows symlinks, so a prefix check on the
    # *resolved* pair is the whole guard. The root itself is refused too: it is
    # a directory, and "read the repo root" is never a file read.
    candidate = (root / repo_relative).resolve()
    if candidate == root:
        return None
    if candidate.is_relative_to(root):
        return candidate
    return None


def _clip(text: Optional[str], limit: int = MAX_TOOL_CHARS) -> str:
    """Trim tool output so one result cannot blow the context window."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, {len(text) - limit} more characters]"


def _to_evidence(row: CodeEmbedding) -> EvidenceChunk:
    return EvidenceChunk(
        file_path=row.file_path,
        symbol_name=row.symbol_name,
        symbol_kind=row.symbol_kind,
        start_line=row.start_line,
        end_line=row.end_line,
        content=row.content,
    )


def _clone_root(db: Session, repo_id: UUID) -> Optional[Path]:
    """Clone directory for this repository, or None if it was never cloned."""
    repo = db.get(ProjectRepository, repo_id)
    if repo is None or not repo.github_owner or not repo.github_name:
        return None
    return Path(settings.CLONE_ROOT_DIR) / repo.github_owner / repo.github_name


def _directory_listing(db: Session, repo_id: UUID, path: str) -> List[str]:
    """Indexed file paths under ``path/``, for when the model names a dir.

    Measured loop-breaker: the model asks `get_file("src/pages")`, gets "no
    file matches", is told to search again, searches, and repeats until the
    step budget dies. Returning the listing turns that dead step into the
    answer ("which files hold the React pages?" *is* a directory question).
    """
    prefix = (path or "").strip().lstrip("./").rstrip("/") + "/"
    if prefix == "/":
        return []
    return [
        row[0]
        for row in (
            db.query(SourceFile.path)
            .filter(
                SourceFile.repo_id == repo_id,
                SourceFile.path.startswith(prefix),
            )
            .order_by(SourceFile.path)
            .limit(30)
            .all()
        )
    ]


def _find_file(db: Session, repo_id: UUID, path: str) -> Optional[SourceFile]:
    """Look up an indexed file by exact path, then by path suffix.

    The suffix pass exists because models routinely answer with a
    half-remembered path (``app/main.py`` for ``backend/app/main.py``); a
    miss here would waste a whole agent turn. It is still scoped to
    ``repo_id``, so it can only ever find this repository's files.
    """
    path = (path or "").strip().lstrip("./")
    if not path:
        return None
    row = (
        db.query(SourceFile)
        .filter(SourceFile.repo_id == repo_id, SourceFile.path == path)
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(SourceFile)
        .filter(
            SourceFile.repo_id == repo_id,
            SourceFile.path.endswith(path),
        )
        .limit(1)
        .first()
    )


def build_tools(
    db: Session, repo_id: UUID
) -> Tuple[List[BaseTool], List[EvidenceChunk]]:
    """Build the four Step-9 tools for one repository.

    Returns the tools for the agent plus the evidence list the retrieval
    tools append to as they run (the caller returns it to the client).
    """
    evidence: List[EvidenceChunk] = []
    seen: set = set()

    def _note(row: CodeEmbedding) -> None:
        if row.id in seen or len(evidence) >= MAX_EVIDENCE:
            return
        seen.add(row.id)
        evidence.append(_to_evidence(row))

    def search_code_tool(query: str) -> str:
        """Semantic search over this repository's indexed code.

        Returns the most similar code chunks with their file path and line
        ranges. Call this first for any question about what the code does,
        where something lives, or how a feature is implemented.
        """
        hits = search_code(db, query=query, repo_id=repo_id, k=6)
        if not hits:
            return (
                "No matching code found in this repository. The question may be "
                "about something that is not here — say so rather than guessing."
            )
        blocks = []
        for hit in hits:
            label = f"{hit.file_path}:{hit.start_line}-{hit.end_line}"
            if hit.symbol_name:
                label += f" [{hit.symbol_kind} {hit.symbol_name}]"
            blocks.append(f"{label}\n{_clip(hit.content, 1500)}")
            _note(hit)
        return "\n\n---\n\n".join(blocks)

    def get_file_tool(path: str) -> str:
        """Read one file from this repository by repo-relative path.

        Example path: 'backend/app/main.py'. Prefers the working tree from
        the clone, falling back to the indexed chunks when the clone is gone.
        """
        row = _find_file(db, repo_id, path)
        if row is None:
            children = _directory_listing(db, repo_id, path)
            if children:
                return (
                    f"{path!r} is a directory, not a file. Files under it: "
                    + ", ".join(children)
                    + ". Call get_file with one full path to read it, "
                    "or answer from this list if that was the question."
                )
            # Neutral wording on purpose: an older version said "call
            # search_code to discover real paths", and the model obeyed it
            # into a search → miss → search loop until the step budget died.
            return (
                f"No file matches {path!r}. Use a path from your search "
                "results, which are known to exist."
            )
        text: Optional[str] = None
        root = _clone_root(db, repo_id)
        if root is not None:
            resolved = safe_clone_path(root, row.path)
            if resolved is not None and resolved.is_file():
                try:
                    text = resolved.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:  # unreadable file: fall through
                    log.warning("could not read %s: %s", row.path, exc)
        if text is None:
            chunks = (
                db.query(CodeEmbedding)
                .filter(
                    CodeEmbedding.repo_id == repo_id,
                    CodeEmbedding.file_path == row.path,
                )
                .order_by(CodeEmbedding.start_line)
                .all()
            )
            text = "\n".join(chunk.content for chunk in chunks)
        if not text:
            return f"{row.path} exists but has no readable content."
        return _clip(f"{row.path} ({row.language}, {row.line_count} lines)\n{text}")

    def get_symbol_tool(name: str) -> str:
        """Look up a function, class, method, or route by (partial) name.

        Returns its file path, inclusive line range and the code body, when
        the repository contains something matching `name`.
        """
        rows = (
            db.query(Symbol, SourceFile.path)
            .join(SourceFile, Symbol.file_id == SourceFile.id)
            .filter(
                Symbol.repo_id == repo_id,
                Symbol.name.ilike(f"%{name}%"),
            )
            .order_by(Symbol.kind, Symbol.name)
            .limit(5)
            .all()
        )
        if not rows:
            return (
                f"No symbol matching {name!r}. Check the spelling against "
                "names in your search results."
            )
        blocks = []
        for sym, file_path in rows:
            header = (
                f"{sym.kind} {sym.name} in {file_path}:{sym.start_line}-{sym.end_line}"
            )
            blocks.append(header)
            chunk = (
                db.query(CodeEmbedding)
                .filter(
                    CodeEmbedding.repo_id == repo_id,
                    CodeEmbedding.file_path == file_path,
                    CodeEmbedding.symbol_name == sym.name,
                )
                .first()
            )
            if chunk is not None:
                blocks.append(_clip(chunk.content, 2000))
                _note(chunk)
        return "\n\n".join(blocks)

    def get_dependencies_tool(path: str) -> str:
        """Show a file's import relationships, one hop in each direction.

        `path` is a repo-relative file path. Returns what this file imports
        and which files import it — one hop only, no transitive walk.
        """
        row = _find_file(db, repo_id, path)
        if row is None:
            children = _directory_listing(db, repo_id, path)
            if children:
                return (
                    f"{path!r} is a directory, not a file — dependencies are "
                    "tracked per file. Files under it: " + ", ".join(children)
                )
            return (
                f"No file matches {path!r}. Use a path from your search "
                "results, which are known to exist."
            )
        imports = [
            r[0]
            for r in (
                db.query(SourceFile.path)
                .join(CodeEdge, CodeEdge.target_id == SourceFile.id)
                .filter(
                    CodeEdge.repo_id == repo_id,
                    CodeEdge.edge_type == "imports",
                    CodeEdge.source_kind == "file",
                    CodeEdge.source_id == row.id,
                )
                .order_by(SourceFile.path)
                .all()
            )
        ]
        imported_by = [
            r[0]
            for r in (
                db.query(SourceFile.path)
                .join(CodeEdge, CodeEdge.source_id == SourceFile.id)
                .filter(
                    CodeEdge.repo_id == repo_id,
                    CodeEdge.edge_type == "imports",
                    CodeEdge.source_kind == "file",
                    CodeEdge.target_id == row.id,
                )
                .order_by(SourceFile.path)
                .all()
            )
        ]
        if not imports and not imported_by:
            return f"{row.path} has no recorded import edges."
        lines = [f"{row.path} imports: " + (", ".join(imports) or "(none)")]
        lines.append("imported by: " + (", ".join(imported_by) or "(none)"))
        return "\n".join(lines)

    return [
        StructuredTool.from_function(
            name="search_code",
            description=(
                "Semantic search over this repository's indexed code. Returns "
                "matching chunks with file path and line ranges. Use first."
            ),
            func=search_code_tool,
        ),
        StructuredTool.from_function(
            name="get_file",
            description=(
                "Read one file from this repository by repo-relative path, "
                "e.g. 'backend/app/main.py'."
            ),
            func=get_file_tool,
        ),
        StructuredTool.from_function(
            name="get_symbol",
            description=(
                "Look up a function/class/method/route by name and return its "
                "location and code body."
            ),
            func=get_symbol_tool,
        ),
        StructuredTool.from_function(
            name="get_dependencies",
            description=(
                "List what a file imports and what imports it (one hop, both "
                "directions), by repo-relative path."
            ),
            func=get_dependencies_tool,
        ),
    ], evidence
