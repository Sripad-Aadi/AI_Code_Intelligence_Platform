"""Language detection from file extensions (v1 — no linguist-style heuristics).

Map a file path to a display language name. Exact filenames (Dockerfile,
Makefile, …) win over suffix matching; unknown extensions fall back to "Other"
so the ingestion histogram still shows how many files had no detectable
grammar. Pure stdlib — keeps Step 4 logic hermetic and testable offline.
"""

from pathlib import Path

# Exact-case-insensitive filenames → language.
FILENAME_LANGUAGE = {
    "dockerfile": "Dockerfile",
    "dockerfile.dev": "Dockerfile",
    "makefile": "Makefile",
    "gnumakefile": "Makefile",
    "bsdmakefile": "Makefile",
    "cmakelists.txt": "CMake",
    "justfile": "Justfile",
    "procfile": "Procfile",
    # Dotfiles have no meaningful suffix in pathlib, so they live here.
    ".env.example": "Text",
    ".editorconfig": "INI",
}

# File extension → language family (v1 display naming; Step 5 picks a
# tree-sitter grammar from the same tag).
EXTENSION_LANGUAGE = {
    # Python
    ".py": "Python",
    ".pyi": "Python",
    ".pyw": "Python",
    # JavaScript / TypeScript
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".tsx": "TypeScript",
    # JVM family
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".groovy": "Groovy",
    ".gradle": "Gradle",
    # C family
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".cs": "C#",
    ".m": "Objective-C",
    ".mm": "Objective-C++",
    ".swift": "Swift",
    ".rs": "Rust",
    ".go": "Go",
    ".zig": "Zig",
    # Web
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".vue": "Vue",
    ".svelte": "Svelte",
    # Scripting / shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".rb": "Ruby",
    ".php": "PHP",
    ".lua": "Lua",
    ".pl": "Perl",
    ".pm": "Perl",
    ".r": "R",
    ".dart": "Dart",
    ".elm": "Elm",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".sql": "SQL",
    # Config / markup / data
    ".json": "JSON",
    ".json5": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".conf": "INI",
    ".xml": "XML",
    ".xsd": "XML",
    ".svg": "SVG",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".ipynb": "Jupyter Notebook",
}


def detect_language(path: Path) -> str:
    """Return the display language name for a source file path."""
    name = path.name.lower()
    if name in FILENAME_LANGUAGE:
        return FILENAME_LANGUAGE[name]
    return EXTENSION_LANGUAGE.get(path.suffix.lower(), "Other")
