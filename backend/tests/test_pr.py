"""Step 14 PR tests: diff parsing, summary contract, output mapping.

All hermetic — no GitHub, no Groq, no database. The live run proves the
provider calls; what is pinned here are the parts that corrupt silently:
hunk parsing, changed-line ranges (deletions must not advance the new-file
cursor), the JSON contract with the model, and risk-level counting.
"""

from uuid import uuid4

import httpx
import pytest
from app.pr_analysis.chain import (
    PRSummary,
    _extract_json,
    _impact_to_output,
)
from app.pr_analysis.diff import (
    ChangedFile,
    get_all_changed_ranges,
    get_changed_line_ranges,
    parse_patch,
)
from app.pr_analysis.impact import AffectedSymbol, ImpactResult
from pydantic import ValidationError

PATCH = """@@ -8,6 +8,7 @@ def handle(items):
     total = 0
+    total += 1
     for item in items:
         if item is None:
             continue
         total += 1
@@ -30,4 +31,3 @@ def other():
     a = 1
-    b = 2
     c = 3
"""


def test_parse_patch_splits_hunks_with_cursors():
    hunks = parse_patch(PATCH)
    assert len(hunks) == 2
    assert (hunks[0].old_start, hunks[0].new_start) == (8, 8)
    assert (hunks[1].old_start, hunks[1].new_start) == (30, 31)


def test_changed_ranges_track_new_file_lines():
    hunks = parse_patch(PATCH)
    assert get_changed_line_ranges(hunks[0]) == [(9, 9)]
    # Pure deletion: no new-file lines changed.
    assert get_changed_line_ranges(hunks[1]) == []
    ranges = get_all_changed_ranges(
        [ChangedFile(file_path="a.py", status="modified", hunks=hunks)]
    )
    assert ranges == {"a.py": [(9, 9)]}


def test_parse_patch_ignores_file_headers():
    hunks = parse_patch("--- a/f.py\n+++ b/f.py\n" + PATCH)
    assert len(hunks) == 2


def test_extract_json_tolerates_fences_and_prose():
    raw = (
        'Here is the review:\n```json\n{"summary_markdown": "ok", '
        '"key_risks": ["a"]}\n```'
    )
    assert _extract_json(raw) == {"summary_markdown": "ok", "key_risks": ["a"]}
    assert _extract_json('{"summary_markdown": "x"}') == {"summary_markdown": "x"}
    with pytest.raises(Exception):
        _extract_json("no json here")


def test_pr_summary_schema_requires_text():
    parsed = PRSummary(summary_markdown="Does X.", key_risks=["r1"])
    assert parsed.summary_markdown == "Does X."
    assert parsed.key_risks == ["r1"]
    assert PRSummary(summary_markdown="x").key_risks == []
    with pytest.raises(ValidationError):
        PRSummary(key_risks=[])


def _impact(levels):
    symbols = []
    scores = {}
    for i, level in enumerate(levels):
        sid = uuid4()
        symbols.append(
            AffectedSymbol(
                symbol_id=sid,
                file_id=uuid4(),
                file_path=f"f{i}.py",
                symbol_name=f"fn{i}",
                symbol_kind="function",
                start_line=1,
                end_line=10,
                changed_lines=[2, 3],
            )
        )
        if level is not None:
            scores[str(sid)] = {"risk_level": level, "probability": 0.9}
    return ImpactResult(
        changed_symbols=symbols,
        affected_files=[{"file_path": "g.py", "reason": "x", "via_symbol": "fn0"}],
        test_files=["test_f0.py"],
        risk_scores=scores,
    )


def test_github_401_means_relink_not_502():
    """A dead stored token must say re-link (409), not baffle with 502."""
    from app.api.pull_requests import _github_error

    request = httpx.Request("GET", "https://api.github.com/x")
    for dead in (401, 403):
        err = _github_error(
            "list pulls",
            httpx.HTTPStatusError(
                "unauthorized",
                request=request,
                response=httpx.Response(dead, request=request),
            ),
        )
        assert err.status_code == 409
        assert "re-link" in err.detail
    missing = _github_error(
        "fetch PR",
        httpx.HTTPStatusError(
            "missing", request=request, response=httpx.Response(404, request=request)
        ),
    )
    assert missing.status_code == 404


def test_impact_to_output_counts_levels_and_keeps_lines():
    repo = uuid4()
    out = _impact_to_output(
        repo, 7, "Add things", [], _impact(["high", "medium", "low", None])
    )
    assert out.repo_id == str(repo)
    assert out.pr_number == 7
    assert (out.high_risk_symbols, out.medium_risk_symbols, out.low_risk_symbols) == (
        1,
        1,
        1,
    )
    assert out.symbols_changed == 4
    assert out.changed_symbols[0].changed_lines == [2, 3]
    assert out.changed_symbols[3].risk_level is None
    assert out.test_files == ["test_f0.py"]
    assert out.summary == "" and out.key_risks == []
