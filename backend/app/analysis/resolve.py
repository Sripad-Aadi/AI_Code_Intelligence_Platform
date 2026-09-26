"""Resolve import specifiers to repo-relative file paths (Step 5).

Best-effort, local-only resolution: stdlib / third-party packages return None
(no in-repo edge). Files are matched against the actual clone on disk, so a
file must exist under the repo root to produce a candidate path.

Python and JS/TS get the full treatment (they dominate real-world repos and
this repo's own codebase); Java/C/C++/Go/Rust/Ruby/PHP/Kotlin/Scala get a
pragmatic best-effort.
"""

from pathlib import Path, PurePosixPath
from typing import Optional

# Candidate file extensions to try when resolving (first hit wins).
_JS_EXTS = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_JS_INDEX = ("index.ts", "index.tsx", "index.js", "index.jsx", "index.mjs")
_PY_EXTS = (".py",)
_PY_PACKAGE = ("__init__.py",)
_JAVA_EXTS = (".java",)
_KT_EXTS = (".kt", ".kts")
_SCALA_EXTS = (".scala",)
_C_EXTS = (".h", ".hpp", ".c", ".cc", ".cpp", ".cxx")
_GO_EXTS = (".go",)
_RS_EXTS = (".rs",)
_RB_EXTS = (".rb",)
_PHP_EXTS = (".php",)


def _try_candidates(
    repo_root: Path, base: Path, rel_parts: tuple, exts: tuple, indexes: tuple = ()
) -> Optional[str]:
    """Return a repo-root-relative posix path if one of the candidates under
    `base` exists on disk; None otherwise. `repo_root` is only needed so the
    result is stable no matter which sub-tree was searched (e.g. a file's own
    directory during relative-import resolution)."""
    prefix = Path(*rel_parts)
    for ext in exts:
        candidate = base / (str(prefix) + ext if ext else str(prefix))
        if candidate.is_file():
            return candidate.relative_to(repo_root).as_posix()
    for index in indexes:
        candidate = base / prefix / index
        if candidate.is_file():
            return candidate.relative_to(repo_root).as_posix()
    return None


def _resolve_python(
    repo_root: Path, file_dir: PurePosixPath, module: str
) -> Optional[str]:
    module = module.strip()
    if module.startswith(".") or module == ".":
        # Relative import: dots map up N levels from the importing file.
        rel_dots = len(module) - len(module.lstrip("."))
        rest = module.lstrip(".").strip(".")
        parts = file_dir.parts
        base_parts = parts[: len(parts) - (rel_dots - 1)] if rel_dots > 1 else parts
        base = repo_root.joinpath(*base_parts)
        if rest:
            mod_parts = tuple(rest.split("."))
            hit = _try_candidates(repo_root, base, mod_parts, _PY_EXTS, _PY_PACKAGE)
            if hit:
                return hit
        # `from . import x` -> any of this dir's modules; check package init.
        hit = _try_candidates(repo_root, base, ("__init__",), (".py",))
        return hit if hit else None

    # Absolute: the importing file may live in a subproject dir (e.g. backend/).
    # Walk each ancestor of the file's directory, ending at the repo root, and
    # try `module path` under it — handles both `repo/app/pkg/mod.py` and
    # monorepo layouts like `repo/backend/app/pkg/mod.py`.
    mod_parts = tuple(module.split("."))
    parts = file_dir.parts
    for i in range(len(parts), -1, -1):
        base = repo_root.joinpath(*parts[:i]) if i else repo_root
        hit = _try_candidates(repo_root, base, mod_parts, _PY_EXTS, _PY_PACKAGE)
        if hit:
            return hit
    return None


def _resolve_js(repo_root: Path, file_dir: PurePosixPath, module: str) -> Optional[str]:
    if not (
        module.startswith(".") or module.startswith("/") or module.startswith("@/")
    ):
        return None  # bare specifier (npm package)
    if module.startswith("@/"):
        module = module[2:]
        base = repo_root
    elif module.startswith("/"):
        module = module.lstrip("/")
        base = repo_root
    else:  # ./ or ../
        base = repo_root.joinpath(*file_dir.parts)
    rel = PurePosixPath(module)
    if rel.name == "" or rel.parts[-1] == ".":
        rel = rel / "index"
    return _try_candidates(repo_root, base, rel.parts, _JS_EXTS, _JS_INDEX)


def _resolve_c(repo_root: Path, file_dir: PurePosixPath, module: str) -> Optional[str]:
    # #include "local.h" -> same dir first, then repo root.
    for base in (repo_root.joinpath(*file_dir.parts), repo_root):
        hit = _try_candidates(repo_root, base, (module,), _C_EXTS)
        if hit:
            return hit
    return None


def resolve_import(
    *,
    grammar: str,
    repo_root: Path,
    file_rel: PurePosixPath,
    module: str,
) -> Optional[str]:
    """Repo-relative path the import points at, or None if not resolvable."""
    if not module:
        return None
    file_dir = file_rel.parent
    if grammar == "python":
        return _resolve_python(repo_root, file_dir, module)
    if grammar in ("javascript", "typescript", "tsx"):
        return _resolve_js(repo_root, file_dir, module)
    if grammar in ("c", "cpp"):
        return _resolve_c(repo_root, file_dir, module)
    if grammar == "java":
        return _try_candidates(
            repo_root, repo_root, tuple(module.split(".")), _JAVA_EXTS, ()
        )
    if grammar == "kotlin":
        return _try_candidates(
            repo_root, repo_root, tuple(module.split(".")), _KT_EXTS, ()
        )
    if grammar == "scala":
        return _try_candidates(
            repo_root, repo_root, tuple(module.split(".")), _SCALA_EXTS, ()
        )
    if grammar == "go":
        parts = tuple(module.split("/"))
        return _try_candidates(repo_root, repo_root, parts, _GO_EXTS)
    if grammar == "rust":
        if module.startswith("crate::"):
            parts = tuple(module[len("crate::") :].split("::"))
            return _try_candidates(repo_root, repo_root, parts, _RS_EXTS, ("mod.rs",))
        return None
    if grammar == "ruby":
        if module.startswith(("./", "../")):
            base = repo_root.joinpath(*file_dir.parts)
            return _try_candidates(
                repo_root, base, PurePosixPath(module).parts, _RB_EXTS
            )
        return _try_candidates(repo_root, repo_root, (module,), _RB_EXTS)
    if grammar == "php":
        cleaned = module.replace("\\", "/")
        parts = tuple(p for p in cleaned.split("/") if p)
        return _try_candidates(repo_root, repo_root, parts, _PHP_EXTS, ())
    return None
