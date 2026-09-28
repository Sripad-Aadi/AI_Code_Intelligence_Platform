"""Step 14 — Diff fetching and parsing for PR impact analysis.

Fetches the PR diff from GitHub, parses changed file/line ranges,
and maps them to Step 5 symbols for impact analysis.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import httpx

log = logging.getLogger(__name__)


@dataclass
class DiffHunk:
    """One contiguous hunk in a unified diff."""

    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]


@dataclass
class ChangedFile:
    """A file changed in the PR with its hunks."""

    file_path: str
    status: str  # added, modified, removed, renamed
    hunks: List[DiffHunk]
    previous_path: Optional[str] = None  # for renamed files


GITHUB_DIFF_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"


async def fetch_pr_diff(
    owner: str,
    repo_name: str,
    pr_number: int,
    access_token: str,
) -> List[ChangedFile]:
    """
    Fetch the list of changed files for a PR from GitHub API.

    Returns list of ChangedFile with parsed hunks.
    """
    url = GITHUB_DIFF_URL.format(owner=owner, repo=repo_name, pr_number=pr_number)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        files_data = resp.json()

    changed_files = []
    for f in files_data:
        filename = f.get("filename", "")
        status = f.get("status", "")
        patch = f.get("patch", "")
        previous_filename = f.get("previous_filename")

        hunks = parse_patch(patch) if patch else []

        changed_files.append(
            ChangedFile(
                file_path=filename,
                status=status,
                hunks=hunks,
                previous_path=previous_filename,
            )
        )

    log.info(
        "Fetched diff for %s/%s PR #%d: %d files changed",
        owner,
        repo_name,
        pr_number,
        len(changed_files),
    )
    return changed_files


# Unified diff line regex: @@ -old_start,old_count +new_start,new_count @@
HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*$")


def parse_patch(patch: str) -> List[DiffHunk]:
    """
    Parse a unified diff patch into DiffHunk objects.

    Each hunk represents a contiguous changed region in one file.
    """
    hunks: List[DiffHunk] = []
    current_file = ""
    lines = patch.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # File header: --- a/path or +++ b/path
        if line.startswith("--- ") or line.startswith("+++ "):
            i += 1
            continue

        # Hunk header
        m = HUNK_HEADER_RE.match(line)
        if m:
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) else 1

            # Collect hunk lines until next hunk or end
            hunk_lines = [line]
            i += 1
            while i < len(lines) and not HUNK_HEADER_RE.match(lines[i]):
                hunk_lines.append(lines[i])
                i += 1

            hunks.append(
                DiffHunk(
                    file_path=current_file,
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=hunk_lines,
                )
            )
            continue

        i += 1

    return hunks


def get_changed_line_ranges(hunk: DiffHunk) -> List[Tuple[int, int]]:
    """
    Extract the new-file line ranges that were added/changed in this hunk.

    Returns list of (start_line, end_line) in the NEW file (1-based, inclusive).
    """
    ranges: List[Tuple[int, int]] = []
    current_line = hunk.new_start
    in_change = False
    change_start = hunk.new_start

    for line in hunk.lines[1:]:  # Skip hunk header
        if line.startswith("+"):
            if not in_change:
                in_change = True
                change_start = current_line
            current_line += 1
        elif line.startswith("-"):
            # Deletion in old file — doesn't advance new file line number
            if in_change:
                # End the current change range
                ranges.append((change_start, current_line - 1))
                in_change = False
            # current_line unchanged
        else:
            # Context line
            if in_change:
                ranges.append((change_start, current_line - 1))
                in_change = False
            current_line += 1

    if in_change:
        ranges.append((change_start, current_line - 1))

    # Merge adjacent/overlapping ranges
    if not ranges:
        return []

    merged = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def get_all_changed_ranges(
    changed_files: List[ChangedFile],
) -> dict[str, List[Tuple[int, int]]]:
    """
    Aggregate all changed line ranges per file (new file line numbers).

    Returns: {file_path: [(start, end), ...]}
    """
    result: dict[str, List[Tuple[int, int]]] = {}
    for cf in changed_files:
        ranges: List[Tuple[int, int]] = []
        for hunk in cf.hunks:
            ranges.extend(get_changed_line_ranges(hunk))
        if ranges:
            result[cf.file_path] = ranges
    return result
