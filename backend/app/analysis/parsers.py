"""Step 5 — structural code analysis with tree-sitter.

Parse indexed files with py-tree-sitter and extract:
  * symbols: functions / classes / methods (name, 1-based start/end lines)
  * imports: raw module specifiers per file
  * routes: framework endpoints where applicable (FastAPI/Flask decorators on
    Python, Express `app.get(...)` on JS/TS)

Boundary accuracy here directly drives Step 7's embedding quality, so the
extraction keeps the *exact* node span of each definition. Pure stdlib + the
two pinned tree-sitter packages — no config/database imports (hermetic,
unit-testable offline).

IMPORTANT: tree-sitter core must be pinned to `==0.21.3` — tree-sitter-languages
1.10.2 calls the pre-0.22 `Language(path, name)` constructor.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Dict, List, Optional

from tree_sitter import Node, Parser
from tree_sitter_languages import get_parser

# ---------------------------------------------------------------------------
# Grammar registry: file suffix -> tree-sitter-languages grammar name.
# Grammars missing from this wheel (c-sharp, swift, dart, zig, scss ...) are
# simply not listed, so those files are recorded but not parsed.
# ---------------------------------------------------------------------------
EXT_GRAMMAR: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".css": "css",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".lua": "lua",
    ".r": "r",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
}

# Which grammar handles which node types -> default symbol kind.
# (kind is overridden to "method" when a function sits inside a class.)
DEFINITION_KINDS: Dict[str, Dict[str, str]] = {
    "python": {"function_definition": "function", "class_definition": "class"},
    "javascript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "tsx": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "class",  # struct / interface / enum
    },
    "rust": {
        "function_item": "function",
        "struct_item": "class",
        "enum_item": "class",
        "trait_item": "class",
        "impl_item": "class",
        "type_item": "class",
    },
    "java": {
        "method_declaration": "method",
        "constructor_declaration": "method",
        "class_declaration": "class",
        "interface_declaration": "class",
        "enum_declaration": "class",
        "record_declaration": "class",
    },
    "c": {"function_definition": "function"},
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "class",
        "union_specifier": "class",
        "enum_specifier": "class",
    },
    "ruby": {
        "method": "method",
        "singleton_method": "method",
        "class": "class",
        "module": "class",
    },
    "php": {
        "function_definition": "function",
        "class_declaration": "class",
        "interface_declaration": "class",
        "trait_declaration": "class",
        "enum_declaration": "class",
    },
    "kotlin": {
        "function_declaration": "function",
        "class_declaration": "class",
        "object_declaration": "class",
        "interface_declaration": "class",
    },
    "scala": {
        "function_definition": "function",
        "class_definition": "class",
        "trait_definition": "class",
        "object_definition": "class",
    },
    "bash": {"function_definition": "function"},
    "r": {"function_definition": "function"},
}

# Ancestor node types that turn a nested "function" into a "method".
CLASS_CONTAINERS: Dict[str, set] = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "tsx": {"class_declaration"},
    "go": {"type_declaration"},
    "rust": {"impl_item"},
    "java": {"class_declaration", "enum_declaration", "record_declaration"},
    "cpp": {"class_specifier", "struct_specifier"},
    "php": {
        "class_declaration",
        "trait_declaration",
    },
    "kotlin": {"class_declaration", "object_declaration"},
    "scala": {"class_definition", "trait_definition", "object_definition"},
}

# Route extraction contexts.
HTTP_METHODS = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "delete": "DELETE",
    "patch": "PATCH",
    "head": "HEAD",
    "options": "OPTIONS",
}
PY_ROUTER_OBJS = {"app", "router", "api", "bp"}

# Node types that count as an identifier when a definition has no "name" field
# (C function declarators, python dotted names, etc).
NAME_LEAF_TYPES = {
    "identifier",
    "property_identifier",
    "type_identifier",
    "field_identifier",
    "simple_identifier",
    "constant",
    "word",
    "function_name",
    "name",
}


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


@dataclass
class ExtractedSymbol:
    name: str
    kind: str  # function | class | method | route
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive


@dataclass
class ExtractedImport:
    module: str
    is_relative: bool


@dataclass
class ParseResult:
    grammar: Optional[str]
    error: Optional[str] = None
    symbols: List[ExtractedSymbol] = field(default_factory=list)
    imports: List[ExtractedImport] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cached parsers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def _parser_for(grammar: str) -> Parser:
    return get_parser(grammar)


def grammar_for_path(path: PurePosixPath) -> Optional[str]:
    """Tree-sitter grammar for a file path, or None (text-only file)."""
    return EXT_GRAMMAR.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _point_row(point) -> int:
    """Row index of a Point. tree-sitter 0.21 returns plain (row, col) tuples;
    newer bindings expose `.row`. Handle both so the pin could move later."""
    row = getattr(point, "row", None)
    return row if row is not None else point[0]


def _span_lines(node: Node) -> tuple[int, int]:
    """1-based inclusive start/end lines of a node (ignoring trailing newline)."""
    start = _point_row(node.start_point) + 1
    text = node.text or b""
    lines = text.count(b"\n")
    trailing = 1 if text.endswith(b"\n") else 0
    return start, start + lines - trailing


def _first_identifier(node: Node) -> Optional[str]:
    """Best-effort name for nodes without a `name` field (walk to a leaf)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in NAME_LEAF_TYPES:
            return (current.text or b"").decode("utf-8", "replace").strip()
        stack.extend(reversed(current.children))
    return None


def _definition_name(grammar: str, node: Node) -> Optional[str]:
    name = node.child_by_field_name("name")
    if name is not None:
        return (name.text or b"").decode("utf-8", "replace").strip() or None
    if grammar in ("c", "cpp") and node.type == "function_definition":
        return _c_function_name(node)
    return _first_identifier(node)


def _c_function_name(node: Node) -> Optional[str]:
    """C/C++ function names live in declarator->...->declarator (the first
    `identifier` leaf would otherwise be the return type)."""
    decl = node.child_by_field_name("declarator")
    guard = 0
    while decl is not None and decl.type == "function_declarator" and guard < 10:
        inner = decl.child_by_field_name("declarator")
        if inner is None:
            break
        decl = inner
        guard += 1
    if decl is None:
        return None
    name = (decl.text or b"").decode("utf-8", "replace").strip().lstrip("*")
    return name or None


def _is_inside_class(node: Node, containers: set) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type in containers:
            return True
        parent = parent.parent
    return False


def _extract_definitions(grammar: str, tree, symbols: List[ExtractedSymbol]) -> None:
    kinds = DEFINITION_KINDS.get(grammar)
    if not kinds:
        return
    containers = CLASS_CONTAINERS.get(grammar, set())

    def route_decorated(node: Node) -> bool:
        """True when a python decorated_definition carries a route decorator."""
        if grammar != "python":
            return False
        for child in node.children:
            if child.type != "decorator":
                continue
            text = (child.text or b"").decode()
            m = _DECORATOR_ROUTE.match(text)
            if m and (
                m.group("attr") in HTTP_METHODS
                or (m.group("attr") == "route" and m.group("obj") in PY_ROUTER_OBJS)
            ):
                return True
        return False

    def walk(node: Node) -> None:
        # JS/TS: `const fn = (...) => {...}` — named arrow functions are real
        # functions, and _definition_name can't reach the name on the rhs.
        if (
            grammar in ("javascript", "typescript", "tsx")
            and node.type == "variable_declarator"
        ):
            value = node.child_by_field_name("value")
            name_node = node.child_by_field_name("name")
            if (
                value is not None
                and value.type == "arrow_function"
                and name_node is not None
            ):
                name = (name_node.text or b"").decode("utf-8", "replace").strip()
                if name:
                    kind = (
                        "method"
                        if containers and _is_inside_class(node, containers)
                        else "function"
                    )
                    start, end = _span_lines(node)
                    symbols.append(ExtractedSymbol(name, kind, start, end))
        kind = kinds.get(node.type)
        if kind is not None:
            # Python route decorators already emit a "route" symbol spanning the
            # whole handler — skip the duplicate inner function symbol.
            if (
                grammar == "python"
                and node.type == "function_definition"
                and node.parent is not None
                and node.parent.type == "decorated_definition"
                and route_decorated(node.parent)
            ):
                pass
            else:
                name = _definition_name(grammar, node)
                if name:
                    if (
                        kind == "function"
                        and containers
                        and _is_inside_class(node, containers)
                    ):
                        kind = "method"
                    start, end = _span_lines(node)
                    symbols.append(ExtractedSymbol(name, kind, start, end))
        for child in node.children:
            walk(child)

    walk(tree.root_node)


# ---------------------------------------------------------------------------
# Imports per grammar
# ---------------------------------------------------------------------------


def _strip_quotes(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def _first_string_child(node: Node) -> Optional[str]:
    """First string literal among a node's *named* children (children would
    include anonymous `(`/`[` tokens in tree-sitter < 0.22)."""
    for child in getattr(node, "named_children", node.children):
        if child.type == "string":
            return _strip_quotes((child.text or b"").decode("utf-8", "replace"))
    return None


def _extract_imports_python(tree, imports: List[ExtractedImport]) -> None:
    seen = set()

    def add(module: str, relative: bool) -> None:
        key = (module, relative)
        if module and key not in seen:
            seen.add(key)
            imports.append(ExtractedImport(module, relative))

    def walk(node: Node) -> None:
        if node.type == "import_statement":
            m = re.match(
                r"^import\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", node.text.decode()
            )
            if m:
                add(m.group(1), False)
        elif node.type == "import_from_statement":
            mod_node = node.child_by_field_name("module_name")
            if mod_node is not None:
                raw = mod_node.text.decode()
                if raw.strip(".") == "":
                    # `from . import x`: module_name is a relative_import holding
                    # only dots — the real module is the first imported name.
                    name_field = node.child_by_field_name("name")
                    first = ""
                    if name_field is not None:
                        first = (
                            name_field.text.decode().split(",")[0].split(".")[0].strip()
                        )
                    add((raw + first) or ".", True)
                else:
                    add(raw, raw.startswith("."))
            else:
                add(".", True)  # defensive fallback for odd relative forms
        for child in node.children:
            walk(child)

    walk(tree.root_node)


def _extract_imports_jslike(tree, imports: List[ExtractedImport]) -> None:
    seen = set()

    def add(module: str) -> None:
        if not module or (module, None) in seen:
            return
        seen.add((module, None))
        imports.append(ExtractedImport(module, module.startswith((".", "/"))))

    def walk(node: Node) -> None:
        if node.type in ("import_statement", "export_statement"):
            source = node.child_by_field_name("source")
            if source is not None:
                add(_strip_quotes(source.text.decode()))
        elif node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if (
                fn is not None
                and fn.type == "identifier"
                and (fn.text or b"").decode() == "require"
            ):
                args = node.child_by_field_name("arguments")
                if args is not None:
                    module = _first_string_child(args)
                    if module:
                        add(module)
        for child in node.children:
            walk(child)

    walk(tree.root_node)


def _extract_imports_generic(
    tree, imports: List[ExtractedImport], node_types: Dict[str, bool]
) -> None:
    """node_types: {node_type: is_relative_default} extracted via fields/text."""
    seen = set()

    def add(module: str, relative: bool) -> None:
        if module and (module, relative) not in seen:
            seen.add((module, relative))
            imports.append(ExtractedImport(module, relative))

    def walk(node: Node) -> None:
        if node.type in node_types:
            text = (node.text or b"").decode().strip()
            if node.type == "preproc_include":  # C/C++
                path = node.child_by_field_name("path")
                if path is not None:
                    add(_strip_quotes(path.text.decode()), True)
            elif node.type == "import_spec":  # Go
                path = node.child_by_field_name("path")
                if path is not None:
                    add(_strip_quotes(path.text.decode()), False)
            elif node.type == "import_header":  # Kotlin
                add(text.replace("import", "", 1).strip(), False)
            elif node.type == "use_declaration":  # Rust
                m = text[len("use") :].strip().rstrip(";")
                add(m, m.startswith(("crate", "super", "self")))
            elif node.type in ("import_declaration",):  # Java, Scala
                if text.startswith("import static"):
                    text = text[len("import static") :]
                else:
                    text = text[len("import") :]
                text = text.strip().rstrip(";").split("{")[0].strip()
                add(text, False)
            elif node.type == "namespace_use_clause":  # PHP
                m = text[3:].strip().rstrip(";")  # strip "use"
                m = m.split(" as ", 1)[0].strip()
                add(m.split("\\", 1)[0] if "\\" in m else m, False)
            elif node.type == "call":  # Ruby require(/relative)
                fn = node.child_by_field_name("method")
                if fn is not None and (fn.text or b"").decode() in (
                    "require",
                    "require_relative",
                ):
                    args = node.child_by_field_name("arguments")
                    if args is not None:
                        module = _first_string_child(args)
                        if module:
                            add(module, True)
        for child in node.children:
            walk(child)

    walk(tree.root_node)


def _extract_imports(grammar: str, tree, imports: List[ExtractedImport]) -> None:
    if grammar == "python":
        _extract_imports_python(tree, imports)
    elif grammar in ("javascript", "typescript", "tsx"):
        _extract_imports_jslike(tree, imports)
    elif grammar in ("c", "cpp"):
        _extract_imports_generic(tree, imports, {"preproc_include": True})
    elif grammar == "go":
        _extract_imports_generic(tree, imports, {"import_spec": False})
    elif grammar == "rust":
        _extract_imports_generic(tree, imports, {"use_declaration": True})
    elif grammar in ("java", "scala"):
        _extract_imports_generic(tree, imports, {"import_declaration": False})
    elif grammar == "kotlin":
        _extract_imports_generic(tree, imports, {"import_header": False})
    elif grammar == "php":
        _extract_imports_generic(tree, imports, {"namespace_use_clause": False})
    elif grammar == "ruby":
        _extract_imports_generic(tree, imports, {"call": True})


# ---------------------------------------------------------------------------
# Framework routes
# ---------------------------------------------------------------------------

_DECORATOR_ROUTE = re.compile(
    r"^@(?P<obj>[A-Za-z_]\w*)\.(?P<attr>[A-Za-z_]\w*)\s*\((?P<args>.*)\)$", re.S
)
_STR = r"['\"](?P<path>[^'\"]*)['\"]"


def _routes_from_python(tree, symbols: List[ExtractedSymbol]) -> None:
    def walk(node: Node) -> None:
        if node.type == "decorated_definition":
            start, end = _span_lines(node)
            for child in node.children:
                if child.type != "decorator":
                    continue
                text = (child.text or b"").decode()
                m = _DECORATOR_ROUTE.match(text)
                if not m:
                    continue
                obj, attr = m.group("obj"), m.group("attr")
                if obj not in PY_ROUTER_OBJS:
                    continue
                if attr in HTTP_METHODS:  # FastAPI: @app.get("/x")
                    pm = re.search(_STR, m.group("args"))
                    if pm:
                        symbols.append(
                            ExtractedSymbol(
                                f"{HTTP_METHODS[attr]} {pm.group('path')}",
                                "route",
                                start,
                                end,
                            )
                        )
                elif attr == "route":  # Flask: @app.route("/x", methods=[...])
                    pm = re.search(_STR, m.group("args"))
                    if pm:
                        methods = re.findall(
                            r"['\"](GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)['\"]",
                            m.group("args"),
                        ) or ["GET"]
                        for method in methods:
                            symbols.append(
                                ExtractedSymbol(
                                    f"{method} {pm.group('path')}",
                                    "route",
                                    start,
                                    end,
                                )
                            )
        for child in node.children:
            walk(child)

    walk(tree.root_node)


def _routes_from_express(tree, symbols: List[ExtractedSymbol]) -> None:
    def walk(node: Node) -> None:
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "member_expression":
                obj = fn.child_by_field_name("object")
                prop = fn.child_by_field_name("property")
                if (
                    obj is not None
                    and (obj.text or b"").decode() in ("app", "router")
                    and prop is not None
                    and (prop.text or b"").decode().lower() in HTTP_METHODS
                ):
                    args = node.child_by_field_name("arguments")
                    if args is not None:
                        path = _first_string_child(args)
                        if path:
                            method = HTTP_METHODS[(prop.text or b"").decode().lower()]
                            start, end = _span_lines(node)
                            symbols.append(
                                ExtractedSymbol(f"{method} {path}", "route", start, end)
                            )
        for child in node.children:
            walk(child)

    walk(tree.root_node)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_source(path: PurePosixPath, source: bytes) -> ParseResult:
    """Parse one file's bytes and return its structural summary.

    Never raises for unparseable content: failures are captured in
    `ParseResult.error` so ingestion can record them per-file and move on.
    """
    grammar = grammar_for_path(path)
    if grammar is None:
        return ParseResult(grammar=None)
    try:
        parser = _parser_for(grammar)
        tree = parser.parse(source)
    except Exception as exc:  # noqa: BLE001
        return ParseResult(grammar=grammar, error=f"{type(exc).__name__}: {exc}")

    symbols: List[ExtractedSymbol] = []
    imports: List[ExtractedImport] = []

    _extract_definitions(grammar, tree, symbols)
    _extract_imports(grammar, tree, imports)
    if grammar == "python":
        _routes_from_python(tree, symbols)
    elif grammar in ("javascript", "typescript", "tsx"):
        _routes_from_express(tree, symbols)

    return ParseResult(grammar=grammar, symbols=symbols, imports=imports)
