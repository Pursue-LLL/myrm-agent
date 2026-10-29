"""Redaction of one file's text as file_read_tool shows it to the model.

A source file names credentials all the time (``total_api_tokens = 0``, ``password: str``) and keeps a secret only
as a string literal, so its text is redacted in source mode: the name-based assignment passes run on the lines that
carry a string literal, every value-shape pass runs everywhere. Any other file (``.env``, YAML, JSON, TOML, INI,
shell, Markdown, a file of unknown type) is redacted in full, because a credential there is a bare assignment.

[INPUT]
- agent.security.redact::redact_sensitive_text (POS: tool output redaction)
- utils.vault_read::path_base (POS: strips the ``:range`` suffix from a path)

[OUTPUT]
- redact_read_view: the redacted text of one path of a read

[POS]
The per-file redaction step of file_read_tool; the tool applies it to every text path, one by one, and redacts the
remaining parts of a read (URL refusals, media text, vault text) as a whole.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from myrm_agent_harness.agent.security.redact import redact_sensitive_text

from ...utils.vault_read import path_base

# Languages whose files hold identifiers and expressions, not configuration.
_SOURCE_SUFFIXES = frozenset(
    {
        ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
        ".go", ".rs", ".java", ".kt", ".scala", ".swift", ".dart",
        ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".lua",
    }
)  # fmt: skip


def redact_read_view(path: str, text: str) -> str:
    """Return ``text``, the content read from ``path`` (a ``:range`` suffix allowed), with its secrets masked."""
    suffix = PurePosixPath(path_base(path)).suffix.lower()
    return redact_sensitive_text(text, source_code=suffix in _SOURCE_SUFFIXES)
