from __future__ import annotations

import logging

from .models import MultimodalQuery

logger = logging.getLogger(__name__)

def _extract_code_execution_network(
    personal_settings_dict: dict[str, object] | None,
) -> bool | None:
    """Extract code execution network permission from personalSettings.

    Returns None when no user preference is set (use server default).
    """
    if not personal_settings_dict:
        return None
    value = personal_settings_dict.get("codeExecutionAllowNetwork")
    if isinstance(value, bool):
        return value
    return None

def _extract_text_from_query(query: MultimodalQuery) -> str:
    """Extract plain text from a multimodal query for DB storage and hygiene checks."""
    if isinstance(query, str):
        return query
    texts = []
    for part in query:
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    return " ".join(texts)

