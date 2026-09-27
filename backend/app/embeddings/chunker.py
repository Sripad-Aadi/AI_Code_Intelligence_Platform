"""Step 7 — code chunking.

Turns one file's source text plus its Step-5 symbols into retrievable
chunks. Pure stdlib: no database, no model, no config import, so it is
unit-testable offline (hermetic, like `app/analysis/parsers.py`).

Two paths, per the plan:

* **the file has symbols** -> one chunk per *top-level* symbol (function,
  class, method, route). Nested symbols are skipped: a class chunk already
  contains its methods' text, so emitting them too would double the index
  without adding recall.
* **the file has no parseable structure** (config, markdown, plain text) ->
  paragraph blocks, or heading sections for markdown.

Anything longer than `MAX_CHUNK_LINES` is windowed with overlap so no chunk
outgrows the embedding model's context budget. Every chunk records the exact
1-based inclusive line range it was cut from — the invariant Step 8/9 rely
on to cite real lines, and this step's stated focus.
"""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

if TYPE_CHECKING:  # typing only — keeps tree-sitter out of this module
    from app.analysis.parsers import ExtractedSymbol

log = logging.getLogger(__name__)

# A chunk longer than this is windowed. 120 lines of code is roughly 1.4k
# tokens, comfortably inside Settings.EMBEDDING_MAX_SEQ_LENGTH (2048), so a
# chunk is embedded whole instead of being silently truncated.
MAX_CHUNK_LINES = 120
WINDOW_LINES = 100
WINDOW_OVERLAP_LINES = 20

# Ceiling on chunks per file. Config/fixture blobs (a 5k-line JSON) would
# otherwise dominate a job's runtime and storage; the cap is logged so a
# truncated file is never silent.
MAX_CHUNKS_PER_FILE = 200

_MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdx")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(\s|$)")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-+)\s*$")


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of a file, with exact line provenance."""

    file_path: str
    language: str
    symbol_kind: Optional[str]  # function|class|method|route, None for text
    symbol_name: Optional[str]  # None for paragraph/section chunks
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    content: str  # verbatim source for [start_line, end_line]


def contextualize(chunk: Chunk) -> str:
    """The text actually handed to the embedding model.

    Raw code retrieves poorly on its own — a bare `return a + b` carries no
    hint about where it lives. Prefixing the repo-relative path and the
    symbol signature (the same metadata stored on the row) is the standard
    fix for code search and is why `content` and the embedded text differ.
    """
    header = [f"# file: {chunk.file_path}"]
    if chunk.symbol_name:
        header.append(
            f"# symbol: {chunk.symbol_kind} {chunk.symbol_name} "
            f"(lines {chunk.start_line}-{chunk.end_line})"
        )
    else:
        header.append(f"# section: lines {chunk.start_line}-{chunk.end_line}")
    return "\n".join(header) + "\n\n" + chunk.content


def chunk_file(
    *,
    file_path: str,
    language: str,
    text: str,
    symbols: Sequence["ExtractedSymbol"] = (),
) -> List[Chunk]:
    """Split one file's text into chunks, symbol-faithful where possible."""
    lines = text.splitlines()
    if not lines:
        return []

    chunks: List[Chunk] = []
    seen: set = set()

    for sym in _top_level_symbols(symbols):
        start, end = _clamp_span(sym.start_line, sym.end_line, len(lines))
        for win_start, win_end in _window_spans(start, end):
            key = (win_start, win_end, sym.kind, sym.name)
            if key in seen:
                continue
            seen.add(key)
            chunk = _make_chunk(
                lines,
                file_path=file_path,
                language=language,
                symbol_kind=sym.kind,
                symbol_name=sym.name,
                start=win_start,
                end=win_end,
            )
            if chunk is not None:
                chunks.append(chunk)

    if not chunks:
        # No symbols, or every symbol span was blank: fall back to text.
        spans = _heading_spans(lines) if _is_markdown(file_path) else None
        if spans is None:
            spans = _paragraph_spans(lines)
        for start, end in spans:
            start, end = _clamp_span(start, end, len(lines))
            for win_start, win_end in _window_spans(start, end):
                chunk = _make_chunk(
                    lines,
                    file_path=file_path,
                    language=language,
                    symbol_kind=None,
                    symbol_name=None,
                    start=win_start,
                    end=win_end,
                )
                if chunk is not None:
                    chunks.append(chunk)

    if len(chunks) > MAX_CHUNKS_PER_FILE:
        log.warning(
            "chunk cap hit for %s: kept %d of %d chunks",
            file_path,
            MAX_CHUNKS_PER_FILE,
            len(chunks),
        )
        chunks = chunks[:MAX_CHUNKS_PER_FILE]
    return chunks


# ---------------------------------------------------------------------------
# Symbol selection
# ---------------------------------------------------------------------------


def _top_level_symbols(symbols: Sequence["ExtractedSymbol"]) -> List["ExtractedSymbol"]:
    """Drop symbols whose line span is contained in another symbol's span.

    tree-sitter reports a class and each of its methods, so containment is
    what tells "this method belongs to that class" apart from two independent
    top-level functions. Identical spans count as siblings, not nesting.
    """
    ordered = sorted(symbols, key=lambda s: (s.start_line, s.end_line, s.name))
    spans = [(s.start_line, s.end_line) for s in ordered]

    top: List["ExtractedSymbol"] = []
    seen: set = set()
    for sym in ordered:
        span = (sym.start_line, sym.end_line)
        nested = any(
            other != span and other[0] <= span[0] and span[1] <= other[1]
            for other in spans
        )
        if nested:
            continue
        key = (sym.kind, sym.name, span)
        if key in seen:
            continue
        seen.add(key)
        top.append(sym)
    return top


# ---------------------------------------------------------------------------
# Span math
# ---------------------------------------------------------------------------


def _clamp_span(start_line: int, end_line: int, total: int) -> Tuple[int, int]:
    """Coerce a span into `1..total`.

    tree-sitter spans are already exact, but a re-read or truncated file must
    never index out of bounds. Returns start > end for an empty file, which
    `_make_chunk` turns into "no chunk".
    """
    if total <= 0:
        return 1, 0
    start = max(1, min(int(start_line), total))
    end = max(start, min(int(end_line), total))
    return start, end


def _trim_blank_edges(lines: List[str], start: int, end: int) -> Tuple[int, int]:
    """Shrink a span past leading/trailing blank lines, keeping it accurate.

    A symbol span often starts one line above the `def` (a decorator or a
    blank separator). Trimming means `content` starts at real code and
    `start_line` still points at it exactly.
    """
    while start <= end and not lines[start - 1].strip():
        start += 1
    while end >= start and not lines[end - 1].strip():
        end -= 1
    return start, end


def _window_spans(start: int, end: int) -> List[Tuple[int, int]]:
    """Split a span that exceeds MAX_CHUNK_LINES into overlapping windows."""
    if end < start:
        return []
    if end - start + 1 <= MAX_CHUNK_LINES:
        return [(start, end)]

    spans: List[Tuple[int, int]] = []
    cursor = start
    while True:
        stop = min(cursor + WINDOW_LINES - 1, end)
        spans.append((cursor, stop))
        if stop >= end:
            return spans
        cursor = stop - WINDOW_OVERLAP_LINES + 1


def _make_chunk(
    lines: List[str],
    *,
    file_path: str,
    language: str,
    symbol_kind: Optional[str],
    symbol_name: Optional[str],
    start: int,
    end: int,
) -> Optional[Chunk]:
    start, end = _trim_blank_edges(lines, start, end)
    if start > end:
        return None
    content = "\n".join(lines[start - 1 : end])
    if not content.strip():
        return None
    return Chunk(
        file_path=file_path,
        language=language,
        symbol_kind=symbol_kind,
        symbol_name=symbol_name,
        start_line=start,
        end_line=end,
        content=content,
    )


# ---------------------------------------------------------------------------
# Text chunking (files with no parseable structure)
# ---------------------------------------------------------------------------


def _is_markdown(file_path: str) -> bool:
    lowered = file_path.lower()
    return lowered.endswith(_MARKDOWN_SUFFIXES)


def _heading_spans(lines: List[str]) -> Optional[List[Tuple[int, int]]]:
    """Split markdown at headings (ATX `#` and setext underlines).

    Returns None when the document has no headings, so the caller can fall
    back to paragraph chunking instead of emitting one giant chunk.
    """
    starts: List[int] = []
    for idx, line in enumerate(lines):
        if _ATX_HEADING.match(line):
            starts.append(idx + 1)
        elif (
            _SETEXT_UNDERLINE.match(line)
            and idx >= 1
            and lines[idx - 1].strip()
            and not _SETEXT_UNDERLINE.match(lines[idx - 1])
        ):
            # Setext heading: the underline promotes the *previous* line.
            starts.append(idx)

    if not starts:
        return None

    ordered = sorted(set(starts))
    spans: List[Tuple[int, int]] = []
    for position, start in enumerate(ordered):
        end = ordered[position + 1] - 1 if position + 1 < len(ordered) else len(lines)
        spans.append((start, end))
    return spans


def _paragraph_spans(lines: List[str]) -> List[Tuple[int, int]]:
    """Group runs of non-blank lines into blocks, then pack blocks together.

    Blocks are never split unless a single block is itself longer than
    MAX_CHUNK_LINES (in which case `_window_spans` handles it), so a
    paragraph stays intact in the chunk that quotes it.
    """
    blocks: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for idx, line in enumerate(lines):
        if line.strip():
            if start is None:
                start = idx + 1
        elif start is not None:
            blocks.append((start, idx))
            start = None
    if start is not None:
        blocks.append((start, len(lines)))

    spans: List[Tuple[int, int]] = []
    cur_start: Optional[int] = None
    cur_end = 0
    for block_start, block_end in blocks:
        if cur_start is None:
            cur_start, cur_end = block_start, block_end
        elif block_end - cur_start + 1 <= MAX_CHUNK_LINES:
            cur_end = block_end
        else:
            spans.append((cur_start, cur_end))
            cur_start, cur_end = block_start, block_end
    if cur_start is not None:
        spans.append((cur_start, cur_end))
    return spans
