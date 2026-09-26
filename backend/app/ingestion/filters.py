"""Repository ingestion filters — what to skip before anything else runs.

Pure stdlib so this module stays hermetic (no config/database imports), which
keeps Step 4's logic unit-testable offline. The ingest Celery task composes
these with language_detect to summarize a repository.
"""

import os
from pathlib import Path
from typing import Generator

# Directories that are never source: VCS metadata, dependencies, build output,
# caches, and bundler output. The os.walk() prunes these in place, so we never
# even descend into them.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "bower_components",
        "vendor",  # PHP/Go vendored dependencies
        "dist",
        "build",
        "out",
        "target",  # Rust/Java build output
        "__pycache__",
        ".venv",
        "venv",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".cargo",
        ".gradle",
        "Pods",
        "DerivedData",
        "__MACOSX",
    }
)

# Files that are never source, regardless of location. `.env` can hold real
# secrets — never ingest it even though we keep `.env.example` (which has an
# extension and counts as documentation).
IGNORED_FILES = frozenset(
    {
        ".env",
        ".gitignore",
        ".dockerignore",
        ".ds_store",
        "thumbs.db",
        "desktop.ini",
    }
)

# Dependency lockfiles — generated, huge, and useless for code intelligence.
LOCKFILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-lock.yml",
        "poetry.lock",
        "pipfile.lock",
        "uv.lock",
        "cargo.lock",
        "gemfile.lock",
        "composer.lock",
        "go.sum",
        "gradle.lockfile",
        "terraform.lock.hcl",
    }
)

# Binary / media extensions — these cannot be parsed as source text.
BINARY_EXTENSIONS = frozenset(
    {
        # images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".avif",
        ".tif",
        ".tiff",
        ".heic",
        # video
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".m4v",
        # audio
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".m4a",
        ".aac",
        ".mid",
        ".midi",
        # fonts
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        # archives / binaries
        ".zip",
        ".gz",
        ".tar",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".o",
        ".a",
        ".class",
        ".jar",
        ".war",
        ".deb",
        ".rpm",
        ".whl",
        ".wasm",
        ".pyc",
        ".pyo",
        ".pyd",
        ".bin",
        ".dat",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".parquet",
        ".arrow",
        ".npy",
        ".npz",
        ".pickle",
        ".pkl",
        ".h5",
        ".hdf5",
        ".onnx",
        ".pb",
        ".pt",
        ".pth",
        ".ckpt",
        ".safetensors",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
    }
)


def is_excluded_dir(dirname: str) -> bool:
    """True if a directory should not be descended into."""
    return dirname in IGNORED_DIRS


def is_excluded(path: Path) -> bool:
    """True if a file should be excluded from ingestion."""
    name = path.name.lower()
    if name in IGNORED_FILES or name in LOCKFILES:
        return True
    if name.endswith(".min.js") or name.endswith(".min.css"):
        return True  # bundled/minified output — pure noise
    return path.suffix.lower() in BINARY_EXTENSIONS


def iter_source_files(root: Path) -> Generator[Path, None, None]:
    """Yield candidate source files under *root* (absolute paths).

    Ignored directories are pruned during the walk (never descended into), and
    excluded files are filtered before yielding. Callers count the items as
    the "indexed" set.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_excluded_dir(d))
        for name in filenames:
            path = Path(dirpath) / name
            if not is_excluded(path):
                yield path
