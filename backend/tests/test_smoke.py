"""Phase 0 smoke tests: the project skeleton itself must be sound."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_app_package_imports():
    """The app package exists and is importable as a package."""
    import app

    assert app.__name__ == "app"


def test_env_example_documents_required_keys():
    """backend/.env.example documents every key the app will rely on."""
    example = BACKEND_ROOT / ".env.example"
    content = example.read_text(encoding="utf-8")
    for key in ("DATABASE_URL", "REDIS_URL", "UPSTASH_TOKEN", "GROQ_API_KEY"):
        assert key in content, f"missing documented key: {key}"


def test_env_file_is_not_staged_for_commit():
    """backend/.env must never be tracked by git (Phase 0 hygiene gate)."""
    tracked = BACKEND_ROOT.joinpath(".env")
    # The file may exist on disk; it just must be absent from the git index.
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--", str(tracked)],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )
    assert result.stdout.strip() == "", "backend/.env is tracked by git"
