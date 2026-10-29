"""Public facade for the secret redaction domain.

Aggregates the redaction engine (``engine.py``) and shared masking helpers
(``masking.py``) behind ``core.security.redact``, exposing a stable public
import surface: ``redact_sensitive_text``, ``redact_for_llm``,
``redact_for_display``, ``RedactingFormatter``, ``set_redact_enabled``, plus the
internal symbols re-exported by the ``agent.security.redact`` facade.

[INPUT]
- engine::redact_sensitive_text, engine::redact_for_llm, engine::redact_for_display, engine::RedactingFormatter and the other public and internal symbols (POS: redaction pipeline and public API of the redactor)
- file_view::redact_file_text (POS: per-file redaction by file type, shared by the tools that show a file's text)
- masking::_mask_token (POS: Leaf value-masking helpers of the runtime redactor)

[OUTPUT]
- redact_sensitive_text / redact_file_text / redact_for_llm / redact_for_display / escape_invisible_unicode / RedactingFormatter / set_redact_enabled — public API
- _mask_token / _redact_pem_block / _redact_value_recursive / _replace_pattern_bounded — internal helpers

[POS]
Public facade of the redaction domain; ``agent/security/redact.py`` re-exports it.
"""

from .engine import (
    RedactingFormatter,
    _redact_pem_block,
    _redact_value_recursive,
    _replace_pattern_bounded,
    escape_invisible_unicode,
    redact_for_display,
    redact_for_llm,
    redact_sensitive_text,
    set_redact_enabled,
)
from .file_view import redact_file_text
from .masking import _mask_token

__all__ = [
    "RedactingFormatter",
    "_mask_token",
    "_redact_pem_block",
    "_redact_value_recursive",
    "_replace_pattern_bounded",
    "escape_invisible_unicode",
    "redact_file_text",
    "redact_for_display",
    "redact_for_llm",
    "redact_sensitive_text",
    "set_redact_enabled",
]
