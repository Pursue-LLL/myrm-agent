"""Personal-settings helpers for attachment text extraction.

[INPUT]
- WebUI ``personalSettings`` dict (via config_loader)

[OUTPUT]
- should_extract_document_text(): whether to parse PDF/Office before LLM

[POS]
Single-tenant attachment extraction policy for Web, channels, and Kanban.
"""

from __future__ import annotations


def should_extract_document_text(
    personal_settings_dict: dict[str, object] | None,
) -> bool:
    """Return whether PDF/Office attachments should be parsed into LLM text.

    Default True when unset (matches nanobot ``extract_document_text`` default).
    """
    if not personal_settings_dict:
        return True
    value = personal_settings_dict.get("extractDocumentText")
    if value is None:
        return True
    return bool(value)
