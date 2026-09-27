"""Hermetic unit tests for Step 7 — chunking.

No database, network, or .env: `app.embeddings.chunker` is pure stdlib. The
embedding model itself is never loaded here (that is verified end to end
through the ingest job, not in unit tests).
"""

from pathlib import PurePosixPath

from app.analysis.parsers import ExtractedSymbol, parse_source
from app.embeddings.chunker import (
    MAX_CHUNK_LINES,
    WINDOW_OVERLAP_LINES,
    chunk_file,
    contextualize,
)

PY_SOURCE = b'''\
"""Module docstring."""

import os

app = None

CONSTANT = 1


def top_level(a, b):
    return a + b


class Service:
    """A service."""

    def method_one(self):
        return CONSTANT

    def method_two(self):
        return top_level(1, 2)


@app.get("/items")
async def get_item():
    return {}
'''


def _python_chunks(source: bytes = PY_SOURCE, path: str = "app/main.py"):
    parsed = parse_source(PurePosixPath(path), source)
    assert parsed.error is None, parsed.error
    return chunk_file(
        file_path=path,
        language="Python",
        text=source.decode(),
        symbols=parsed.symbols,
    )


# ---------------------------------------------------------------------------
# Symbol-faithful chunking
# ---------------------------------------------------------------------------


def test_chunk_per_top_level_symbol():
    chunks = _python_chunks()
    names = [c.symbol_name for c in chunks]
    # The class is chunked whole; its two methods are not emitted separately.
    # Route symbols are named "<METHOD> <path>" by the Step 5 parser.
    assert names == ["top_level", "Service", "GET /items"]
    assert [c.symbol_kind for c in chunks] == ["function", "class", "route"]


def test_symbol_span_matches_source_exactly():
    lines = PY_SOURCE.decode().splitlines()
    for chunk in _python_chunks():
        assert chunk.content == "\n".join(
            lines[chunk.start_line - 1 : chunk.end_line]
        ), f"{chunk.symbol_name} content drifted from its line range"
        assert chunk.start_line >= 1
        assert chunk.end_line <= len(lines)


def test_symbol_chunks_carry_metadata():
    chunks = {c.symbol_name: c for c in _python_chunks()}
    service = chunks["Service"]
    assert service.file_path == "app/main.py"
    assert service.language == "Python"
    # The class body is in the chunk verbatim.
    assert "def method_one(self):" in service.content
    assert "def method_two(self):" in service.content


def test_decorator_line_is_inside_the_route_chunk():
    chunks = {c.symbol_name: c for c in _python_chunks()}
    route = chunks["GET /items"]
    assert route.content.startswith('@app.get("/items")')


# ---------------------------------------------------------------------------
# Oversized symbols are windowed, with exact per-window metadata
# ---------------------------------------------------------------------------


def _big_function(lines: int) -> bytes:
    body = "\n".join(f"    x{i} = {i}" for i in range(lines))
    return f"def big():\n{body}\n".encode()


def test_oversized_symbol_is_windowed_with_overlap():
    text = _big_function(MAX_CHUNK_LINES * 2).decode()
    parsed = parse_source(PurePosixPath("big.py"), text.encode())
    chunks = chunk_file(
        file_path="big.py", language="Python", text=text, symbols=parsed.symbols
    )
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.end_line - chunk.start_line + 1 <= MAX_CHUNK_LINES
    for previous, following in zip(chunks, chunks[1:]):
        assert previous.end_line - following.start_line + 1 == WINDOW_OVERLAP_LINES


def test_oversized_symbol_windows_are_contiguous_and_cover_the_span():
    total = MAX_CHUNK_LINES * 2 + 37
    text = _big_function(total).decode()
    parsed = parse_source(PurePosixPath("big.py"), text.encode())
    assert parsed.symbols, "expected big() to parse"
    chunks = chunk_file(
        file_path="big.py", language="Python", text=text, symbols=parsed.symbols
    )
    assert len(chunks) > 1
    assert chunks[0].start_line == parsed.symbols[0].start_line
    assert chunks[-1].end_line == parsed.symbols[0].end_line
    for previous, following in zip(chunks, chunks[1:]):
        assert following.start_line <= previous.end_line + 1  # no gap
    lines = text.splitlines()
    for chunk in chunks:
        assert chunk.content == "\n".join(lines[chunk.start_line - 1 : chunk.end_line])


def test_small_symbol_is_not_windowed():
    symbol = ExtractedSymbol(name="tiny", kind="function", start_line=1, end_line=3)
    chunks = chunk_file(
        file_path="t.py",
        language="Python",
        text="def tiny():\n    return 1\n    # end\n",
        symbols=[symbol],
    )
    assert len(chunks) == 1
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 3)


# ---------------------------------------------------------------------------
# Nesting / sibling edge cases
# ---------------------------------------------------------------------------


def test_identical_spans_are_siblings_not_nesting():
    a = ExtractedSymbol(name="a", kind="function", start_line=1, end_line=4)
    b = ExtractedSymbol(name="b", kind="function", start_line=1, end_line=4)
    chunks = chunk_file(
        file_path="t.py",
        language="Python",
        text="def a():\n    pass\n\ndef b():\n    pass\n",
        symbols=[a, b],
    )
    assert [c.symbol_name for c in chunks] == ["a", "b"]


def test_span_past_end_of_file_is_clamped():
    chunks = chunk_file(
        file_path="t.py",
        language="Python",
        text="def only():\n    return 1\n",
        symbols=[
            ExtractedSymbol(name="only", kind="function", start_line=1, end_line=99)
        ],
    )
    assert len(chunks) == 1
    assert chunks[0].end_line == 2


def test_blank_symbol_span_falls_back_to_text_chunking():
    """A symbol whose span is all whitespace yields no symbol chunk; the file
    is then chunked as text (its non-blank lines), with no symbol metadata."""
    chunks = chunk_file(
        file_path="t.py",
        language="Python",
        text="\n\n\nreal()\n",
        symbols=[
            ExtractedSymbol(name="blank", kind="function", start_line=1, end_line=3)
        ],
    )
    assert len(chunks) == 1
    assert chunks[0].symbol_name is None
    assert chunks[0].symbol_kind is None
    assert chunks[0].content == "real()"
    assert (chunks[0].start_line, chunks[0].end_line) == (4, 4)


# ---------------------------------------------------------------------------
# Files with no parseable structure
# ---------------------------------------------------------------------------


MARKDOWN = """\
# Title

Intro paragraph.

## Setup

Install it.

Then configure it.

## Usage

Run it.
"""


def test_markdown_splits_on_headings():
    chunks = chunk_file(
        file_path="README.md", language="Markdown", text=MARKDOWN, symbols=[]
    )
    lines = MARKDOWN.splitlines()
    assert len(chunks) == 3
    assert [c.start_line for c in chunks] == [1, 5, 11]
    assert chunks[0].content.startswith("# Title")
    assert chunks[1].content.startswith("## Setup")
    assert chunks[2].content.startswith("## Usage")
    assert all(c.symbol_name is None and c.symbol_kind is None for c in chunks)
    for chunk in chunks:
        assert chunk.content == "\n".join(lines[chunk.start_line - 1 : chunk.end_line])


def test_markdown_without_headings_falls_back_to_paragraphs():
    text = "just a paragraph\nstill the same one\n\nsecond block"
    chunks = chunk_file(
        file_path="notes.md", language="Markdown", text=text, symbols=[]
    )
    # No heading to split on, and it is short enough to pack into one chunk.
    assert len(chunks) == 1
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 4)
    assert chunks[0].content == text


def test_long_text_splits_at_paragraph_boundaries():
    block = "\n".join(f"line {i}" for i in range(80))
    text = f"{block}\n\n{block}\n\n{block}\n"
    chunks = chunk_file(file_path="notes.txt", language="Text", text=text, symbols=[])
    # Three 80-line blocks, blank line between each: no block can be merged
    # into a neighbour without exceeding MAX_CHUNK_LINES, so each is its own
    # chunk and every chunk starts on a real content line.
    assert [c.start_line for c in chunks] == [1, 82, 163]
    for chunk in chunks:
        assert chunk.end_line - chunk.start_line + 1 == 80


def test_plain_text_packs_paragraphs_into_one_chunk():
    text = "\n\n".join(f"block {i}\nline" for i in range(10))
    chunks = chunk_file(file_path="notes.txt", language="Text", text=text, symbols=[])
    assert len(chunks) == 1
    assert chunks[0].content == text


def test_oversized_paragraph_is_windowed():
    text = "\n".join(f"line {i}" for i in range(MAX_CHUNK_LINES + 50))
    chunks = chunk_file(file_path="notes.txt", language="Text", text=text, symbols=[])
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.end_line - chunk.start_line + 1 <= MAX_CHUNK_LINES


def test_empty_file_yields_no_chunks():
    assert chunk_file(file_path="e.py", language="Python", text="", symbols=[]) == []
    assert (
        chunk_file(file_path="e.py", language="Python", text="\n\n", symbols=[]) == []
    )


# ---------------------------------------------------------------------------
# contextualize — what actually gets embedded
# ---------------------------------------------------------------------------


def test_contextualize_includes_path_and_symbol():
    chunk = {c.symbol_name: c for c in _python_chunks()}["top_level"]
    text = contextualize(chunk)
    assert text.startswith("# file: app/main.py")
    assert "# symbol: function top_level" in text
    assert f"lines {chunk.start_line}-{chunk.end_line}" in text
    assert text.endswith(chunk.content)


def test_contextualize_marks_text_chunks_as_sections():
    chunk = chunk_file(
        file_path="README.md", language="Markdown", text=MARKDOWN, symbols=[]
    )[0]
    text = contextualize(chunk)
    assert "# section: lines 1-3" in text
    assert "# symbol:" not in text
