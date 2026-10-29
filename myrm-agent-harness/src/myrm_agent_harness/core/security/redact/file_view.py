"""Redaction of text taken from one file, by the type of that file.

A source file names credentials all the time (``total_api_tokens = 0``, ``password: str``) and keeps a secret only
as a string literal, so its text is redacted in source mode: the name-based assignment passes run on the lines that
carry a string literal, every value-shape pass runs everywhere. Any other file (``.env``, YAML, JSON, TOML, INI,
shell, Markdown, a file of unknown type) is redacted in full, because a credential there is a bare assignment.

[INPUT]
- engine::redact_sensitive_text (POS: redaction pipeline)

[OUTPUT]
- redact_file_text: the redacted text taken from one path

[POS]
The per-file redaction step shared by the tools that show a file's text to the model (file_read_tool, grep_tool), so
the same line of code reads the same through either.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from .engine import redact_sensitive_text

# Languages whose files hold identifiers and expressions, not configuration.
_SOURCE_SUFFIXES = frozenset(
    {
        ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
        ".go", ".rs", ".java", ".kt", ".scala", ".swift", ".dart",
        ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".lua",
    }
)  # fmt: skip


def redact_file_text(path: str, text: str) -> str:
    """Return ``text``, taken from the file at ``path`` (no ``:range`` suffix), with its secrets masked."""
    suffix = PurePosixPath(path).suffix.lower()
    return redact_sensitive_text(text, source_code=suffix in _SOURCE_SUFFIXES)
