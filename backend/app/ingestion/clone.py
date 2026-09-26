"""Shallow cloning of GitHub repositories onto the server's own disk (Step 3).

Plain `git clone --depth=1` — no Docker volume needed. Clones land under
`CLONE_ROOT_DIR/<owner>/<repo>` so Steps 4+ (ingestion/parsing) can read them
from disk, and re-cloning replaces the previous contents.
"""

import shutil
import subprocess
from pathlib import Path

from app.config import settings


def clone_shallow(repo_url: str, dest: Path) -> Path:
    """Shallow-clone a repo (https URL) into `CLONE_ROOT_DIR/dest`, replacing
    prior contents.

    `dest` is a path *relative to* the configured clone root (the helper
    prepends it). Returns the clone root. Raises subprocess.CalledProcessError
    on failure (e.g. bad URL, network, or insufficient permissions).
    """
    clone_root = Path(settings.CLONE_ROOT_DIR)
    target = clone_root / dest
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(target)],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,  # Large repos on slow links need headroom
    )
    return target
