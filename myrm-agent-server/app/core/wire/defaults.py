"""Default model kwargs for wire-specific model families.

[INPUT]
- none (imports no other project module)

[OUTPUT]
- apply_wire_defaults: merges wire-aware defaults into model_kwargs without overwriting explicit user values

[POS]
Defaults layer of the wire routing: adds the request defaults that the `responses` wire needs for muse-spark models and the
gateway headers and provider hint for Vercel AI Gateway endpoints, while explicit user values always win.
"""

from __future__ import annotations

import re
from typing import Any

_MUSE_SPARK_PATTERN = re.compile(r"^muse-spark", re.IGNORECASE)


def apply_wire_defaults(
    model: str,
    model_kwargs: dict[str, Any] | None,
    wire_protocol: str,
    *,
    base_url: str | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    """Merge wire-aware defaults into model_kwargs without overwriting explicit user values."""
    merged = dict(model_kwargs or {})
    normalized = model.rsplit("/", 1)[-1] if "/" in model else model
    if wire_protocol == "responses" and _MUSE_SPARK_PATTERN.search(normalized):
        extra_body = dict(merged.get("extra_body") or {}) if isinstance(merged.get("extra_body"), dict) else {}
        reasoning = extra_body.get("reasoning")
        if not isinstance(reasoning, dict):
            extra_body["reasoning"] = {"effort": "low"}
        if "include" not in extra_body:
            extra_body["include"] = ["reasoning.encrypted_content"]
        merged["extra_body"] = extra_body
        if merged.get("max_tokens") is None and merged.get("max_output_tokens") is None:
            merged.setdefault("max_tokens", 512)

    if provider_id == "vercel_ai_gateway" or (base_url and "ai-gateway.vercel.sh" in base_url):
        raw_headers = merged.get("extra_headers")
        extra_headers = dict(raw_headers) if isinstance(raw_headers, dict) else {}
        extra_headers.setdefault("HTTP-Referer", "https://myrm.ai")
        extra_headers.setdefault("X-Title", "Myrm Agent")
        extra_headers.setdefault("User-Agent", "Myrm/1.0 (Vercel-AI-Gateway-Client)")
        merged["extra_headers"] = extra_headers
        merged.setdefault("custom_llm_provider", "openai")

    return merged
