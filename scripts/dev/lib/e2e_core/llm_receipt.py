"""LLMReceipt — mechanical audit receipt for LIVE Chrome E2E signoff (§19.12 W5).

Emits ``model_id`` + ``assistant_snippet`` + private ``api_port`` so the detach
log is grep-able for "what model answered and what it said" without opening the
browser. Mirrors §23.4 W5 Exit Gate: log must contain an ``LLM_RECEIPT=`` line.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit

_ASSISTANT_SNIPPET_MAX_CHARS = 120


def _api_port(api_url: str) -> int | None:
    return urlsplit(api_url).port


def _resolve_active_model_id(providers_value: dict[str, object]) -> str:
    """Extract ``providerId/modelId`` from the providers config defaultModelConfig."""
    default_cfg = providers_value.get("defaultModelConfig")
    if not isinstance(default_cfg, dict):
        return ""
    base = default_cfg.get("baseModel")
    if not isinstance(base, dict):
        return ""
    primary = base.get("primary")
    if not isinstance(primary, dict):
        return ""
    provider_id = str(primary.get("providerId") or "").strip()
    model_id = str(primary.get("modelId") or "").strip()
    if provider_id and model_id:
        return f"{provider_id}/{model_id}"
    return model_id or provider_id


def _assistant_snippet(messages: list[dict[str, object]]) -> str:
    """Return the newest non-empty assistant text, capped for one-line grep."""
    for message in reversed(messages):
        role = str(message.get("role") or "").strip().lower()
        if role != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            text_parts = [
                str(part.get("text") or "").strip()
                for part in content
                if isinstance(part, dict)
                and str(part.get("type") or "") == "text"
            ]
            text = " ".join(part for part in text_parts if part).strip()
        else:
            text = ""
        if text:
            return text[:_ASSISTANT_SNIPPET_MAX_CHARS]
    return ""


def emit_llm_receipt(
    *,
    chat_id: str,
    api_url: str | None = None,
) -> dict[str, object]:
    """Collect and print the LLMReceipt line for a signed-off LIVE chat.

    Writes ``LLM_RECEIPT={"model_id": ..., "assistant_snippet": ..., "api_port": ...}``
    to stdout (captured by the detach log) and returns the dict for assertions.
    """
    from cdp_chat_support import (
        fetch_chat_messages,
        fetch_config_value,
        get_e2e_api_url,
    )

    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    providers_value = fetch_config_value("providers", api_url=resolved_api)
    messages = fetch_chat_messages(chat_id, api_url=resolved_api)
    receipt: dict[str, object] = {
        "model_id": _resolve_active_model_id(providers_value),
        "assistant_snippet": _assistant_snippet(messages),
        "api_port": _api_port(resolved_api),
    }
    sys.stdout.write(f"LLM_RECEIPT={json.dumps(receipt, ensure_ascii=False)}\n")
    sys.stdout.flush()
    return receipt
