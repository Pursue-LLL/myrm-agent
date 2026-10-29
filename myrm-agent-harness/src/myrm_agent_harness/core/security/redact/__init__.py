"""Public facade for the secret redaction domain.

Aggregates the redaction engine (``engine.py``), the command-line entry
(``command_line.py``) and shared masking helpers (``masking.py``) behind
``core.security.redact``, exposing a stable public import surface:
``redact_sensitive_text``, ``redact_command_line``, ``command_preview``, ``redact_for_llm``,
``redact_for_display``, ``redact_field_text``, ``redact_nested``, ``RedactingFormatter``,
``set_redact_enabled``, plus the internal symbols re-exported by the ``agent.security.redact`` facade.

[INPUT]
- engine::redact_sensitive_text, engine::redact_for_llm, engine::redact_for_display, engine::redact_field_text, engine::RedactingFormatter and the other public and internal symbols (POS: redaction pipeline and public API of the redactor)
- bounded_replace::_replace_pattern_bounded (POS: Bounded regex replacement, the ReDoS guard of every redaction pass)
- command_line::redact_command_line, command_line::command_preview (POS: Entry of the commands the audit log and the background-job registry keep, and the preview of the commands a log line quotes)
- file_view::redact_file_text (POS: per-file redaction by file type, shared by the tools that show a file's text)
- masking::_mask_token (POS: Leaf value-masking helpers of the runtime redactor)
- nested::redact_nested (POS: Shared walker of the redaction domain: bounded in depth, cuts a container that holds itself)

[OUTPUT]
- redact_sensitive_text / redact_command_line / command_preview / redact_file_text / redact_for_llm / redact_for_display / redact_field_text / redact_nested / escape_invisible_unicode / RedactingFormatter / set_redact_enabled — public API
- _mask_token / _redact_pem_block / _replace_pattern_bounded — internal helpers

[POS]
Public facade of the redaction domain; ``agent/security/redact.py`` re-exports it.
"""

from .bounded_replace import _replace_pattern_bounded
from .command_line import command_preview, redact_command_line
from .engine import (
    RedactingFormatter,
    _redact_pem_block,
    escape_invisible_unicode,
    redact_field_text,
    redact_for_display,
    redact_for_llm,
    redact_sensitive_text,
    set_redact_enabled,
)
from .file_view import redact_file_text
from .masking import _mask_token
from .nested import redact_nested

__all__ = [
    "RedactingFormatter",
    "_mask_token",
    "_redact_pem_block",
    "_replace_pattern_bounded",
    "command_preview",
    "escape_invisible_unicode",
    "redact_command_line",
    "redact_field_text",
    "redact_file_text",
    "redact_for_display",
    "redact_for_llm",
    "redact_nested",
    "redact_sensitive_text",
    "set_redact_enabled",
]
