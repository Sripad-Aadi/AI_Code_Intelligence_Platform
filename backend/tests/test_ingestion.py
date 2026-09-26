"""Hermetic unit tests for Step 4 — ingestion filters + language detection.

No database, network, or .env needed: `app.ingestion.filters` and
`app.ingestion.language_detect` are pure-stdlib modules by design.
"""

from pathlib import Path

from app.ingestion.filters import is_excluded, is_excluded_dir, iter_source_files
from app.ingestion.language_detect import detect_language


def test_is_excluded_dir_known() -> None:
    assert is_excluded_dir("node_modules")
    assert is_excluded_dir(".git")
    assert is_excluded_dir("dist")
    assert is_excluded_dir("build")
    assert is_excluded_dir("vendor")
    assert is_excluded_dir("__pycache__")
    assert not is_excluded_dir("src")


def test_is_excluded_files() -> None:
    assert is_excluded(Path("package-lock.json"))
    assert is_excluded(Path("yarn.lock"))
    assert is_excluded(Path("logo.png"))
    assert is_excluded(Path("movie.mp4"))
    assert is_excluded(Path("font.woff2"))
    assert is_excluded(Path("bundle.min.js"))
    assert is_excluded(Path(".env"))  # could hold real secrets
    assert not is_excluded(Path("src/main.py"))
    assert not is_excluded(Path("README.md"))


def test_iter_source_files_prunes_and_filters(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    good = [
        repo / "src" / "main.py",
        repo / "src" / "util" / "helper.ts",
        repo / "README.md",
    ]
    bad = [
        repo / "node_modules" / "pkg" / "index.js",
        repo / "dist" / "bundle.js",
        repo / ".git" / "config",
        repo / "src" / "__pycache__" / "main.cpython-312.pyc",
        repo / "package-lock.json",
        repo / "logo.png",
        repo / ".env",
    ]
    for path in good + bad:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    found = sorted(p.relative_to(repo).as_posix() for p in iter_source_files(repo))
    assert found == ["README.md", "src/main.py", "src/util/helper.ts"]


def test_detect_language_by_extension() -> None:
    assert detect_language(Path("main.py")) == "Python"
    assert detect_language(Path("app.tsx")) == "TypeScript"
    assert detect_language(Path("server.js")) == "JavaScript"
    assert detect_language(Path("model.go")) == "Go"
    assert detect_language(Path("db.sql")) == "SQL"
    assert detect_language(Path("README.md")) == "Markdown"
    assert detect_language(Path("config.json")) == "JSON"
    assert detect_language(Path("data.unknown_ext")) == "Other"


def test_detect_language_by_filename() -> None:
    assert detect_language(Path("Dockerfile")) == "Dockerfile"
    assert detect_language(Path("Makefile")) == "Makefile"
    assert detect_language(Path(".env.example")) == "Text"
    assert detect_language(Path(".editorconfig")) == "INI"


def test_detect_language_case_insensitive_and_nested() -> None:
    assert detect_language(Path("SRC/MAIN.PY")) == "Python"
    assert detect_language(Path("a/b/c/CMakeLists.txt")) == "CMake"
