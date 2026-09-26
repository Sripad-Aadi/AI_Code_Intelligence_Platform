"""Hermetic unit tests for Step 5 — tree-sitter parsing + import resolution.

No database, network, or .env needed: `app.analysis.*` only imports the pinned
tree-sitter packages and stdlib.
"""

from pathlib import Path, PurePosixPath

from app.analysis.parsers import parse_source
from app.analysis.resolve import resolve_import

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


PY_SOURCE = b'''\
"""A module docstring."""

import os
import app.models
from . import local
from ..common import util as u

app = None
router = None


def top_level(a, b):
    return a + b


class Service:
    """A service."""

    def method_one(self):
        pass

    def method_two(self):
        return top_level(1, 2)


@app.get("/items/{item_id}")
async def get_item(item_id: int):
    return {"item": item_id}


@decorator
def decorated_plain():
    pass
'''


def test_parse_python_symbols() -> None:
    result = parse_source(PurePosixPath("app/main.py"), PY_SOURCE)
    assert result.grammar == "python"
    assert result.error is None

    names = [(s.name, s.kind) for s in result.symbols]
    assert ("top_level", "function") in names
    assert ("Service", "class") in names
    assert ("method_one", "method") in names
    assert ("method_two", "method") in names
    assert ("decorated_plain", "function") in names
    # Route handler: one "route" symbol spans it; no duplicate function symbol.
    assert ("GET /items/{item_id}", "route") in names
    assert ("get_item", "function") not in names

    service = next(s for s in result.symbols if s.name == "Service")
    method = next(s for s in result.symbols if s.name == "method_one")
    assert service.kind == "class"
    assert method.kind == "method"
    assert method.start_line > service.start_line
    assert method.end_line < service.end_line


def test_parse_python_imports() -> None:
    result = parse_source(PurePosixPath("app/main.py"), PY_SOURCE)
    mods = [(i.module, i.is_relative) for i in result.imports]
    assert ("os", False) in mods
    assert ("app.models", False) in mods
    assert (".local", True) in mods  # `from . import local`
    assert ("..common", True) in mods


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


TS_SOURCE = b"""\
import express from "express";
import { Button } from "./components/Button";
import type { Api } from "../types";

let app = express();

export function helper(x: number): number {
  return x * 2;
}

export class Widget {
  render(): string {
    return "hi";
  }
}

const buildLabel = (n: number): string => `n=${n}`;

app.get("/users/:id", (req, res) => {
  res.json({ id: req.params.id });
});
"""


def test_parse_typescript() -> None:
    result = parse_source(PurePosixPath("src/server.ts"), TS_SOURCE)
    assert result.grammar == "typescript"
    assert result.error is None

    names = [(s.name, s.kind) for s in result.symbols]
    assert ("helper", "function") in names
    assert ("Widget", "class") in names
    assert ("render", "method") in names
    assert ("buildLabel", "function") in names  # named arrow function
    assert ("GET /users/:id", "route") in names
    assert ("req", "function") not in names  # no bogus param symbols

    mods = [i.module for i in result.imports]
    assert "./components/Button" in mods
    assert "../types" in mods
    assert "express" in mods


# ---------------------------------------------------------------------------
# Other languages
# ---------------------------------------------------------------------------


def test_parse_go() -> None:
    src = b"""package main

type Person struct {
    Name string
}

func New(name string) Person {
    return Person{Name: name}
}

func (p Person) Greet() string {
    return "hi " + p.Name
}
"""
    result = parse_source(PurePosixPath("main.go"), src)
    assert result.grammar == "go"
    names = [(s.name, s.kind) for s in result.symbols]
    assert ("Person", "class") in names
    assert ("New", "function") in names
    assert ("Greet", "method") in names


def test_parse_c() -> None:
    src = b"int add(int a, int b) {\n  return a + b;\n}\n"
    result = parse_source(PurePosixPath("math.c"), src)
    assert result.grammar == "c"
    assert result.symbols[0].name == "add"
    assert result.symbols[0].kind == "function"
    assert (result.symbols[0].start_line, result.symbols[0].end_line) == (1, 3)


def test_parse_rust_routes_none() -> None:
    src = b"use crate::models::User;\nfn main() {}\n"
    result = parse_source(PurePosixPath("main.rs"), src)
    assert result.grammar == "rust"
    assert [s.name for s in result.symbols] == ["main"]
    assert [(i.module, i.is_relative) for i in result.imports] == [
        ("crate::models::User", True)
    ]


def test_parse_text_file_no_grammar() -> None:
    result = parse_source(PurePosixPath("README.md"), b"# Hi\n")
    assert result.grammar is None
    assert result.symbols == []
    assert result.imports == []


# ---------------------------------------------------------------------------
# Import resolution
# ---------------------------------------------------------------------------


def test_resolve_python(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "app" / "models").mkdir(parents=True)
    (root / "app" / "models" / "user.py").write_text("", encoding="utf-8")
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "utils").mkdir()
    (root / "utils" / "helpers.py").write_text("", encoding="utf-8")
    (root / "app" / "main.py").write_text("", encoding="utf-8")

    r = resolve_import(
        grammar="python",
        repo_root=root,
        file_rel=PurePosixPath("app/main.py"),
        module="app.models.user",
    )
    assert r == "app/models/user.py"

    r = resolve_import(
        grammar="python",
        repo_root=root,
        file_rel=PurePosixPath("app/main.py"),
        module=".models.user",
    )
    assert r == "app/models/user.py"

    r = resolve_import(
        grammar="python",
        repo_root=root,
        file_rel=PurePosixPath("app/main.py"),
        module="os",
    )
    assert r is None  # stdlib


def test_resolve_python_subproject_dir(tmp_path: Path) -> None:
    """Absolute imports resolve under a subproject dir (e.g. backend/)."""
    root = tmp_path / "repo"
    (root / "backend" / "app" / "db").mkdir(parents=True)
    (root / "backend" / "app" / "main.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "db" / "session.py").write_text("", encoding="utf-8")

    r = resolve_import(
        grammar="python",
        repo_root=root,
        file_rel=PurePosixPath("backend/app/main.py"),
        module="app.db.session",
    )
    assert r == "backend/app/db/session.py"

    # Flat layout must keep working (repo root tried last).
    r = resolve_import(
        grammar="python",
        repo_root=root,
        file_rel=PurePosixPath("backend/app/main.py"),
        module="os.path",
    )
    assert r is None  # stdlib single part


def test_resolve_typescript(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src" / "components").mkdir(parents=True)
    (root / "src" / "components" / "Button.tsx").write_text("", encoding="utf-8")
    (root / "src" / "server.ts").write_text("", encoding="utf-8")

    r = resolve_import(
        grammar="typescript",
        repo_root=root,
        file_rel=PurePosixPath("src/server.ts"),
        module="./components/Button",
    )
    assert r == "src/components/Button.tsx"

    r = resolve_import(
        grammar="typescript",
        repo_root=root,
        file_rel=PurePosixPath("src/server.ts"),
        module="express",
    )
    assert r is None  # npm package


def test_resolve_java(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "com" / "example").mkdir(parents=True)
    (root / "com" / "example" / "Main.java").write_text("", encoding="utf-8")

    r = resolve_import(
        grammar="java",
        repo_root=root,
        file_rel=PurePosixPath("com/example/App.java"),
        module="com.example.Main",
    )
    assert r == "com/example/Main.java"
