"""Default model kwargs for wire-specific model families."""

from __future__ import annotations

import re
from typing import Any

_MUSE_SPARK_PATTERN = re.compile(r"^muse-spark", re.IGNORECASE)


def apply_wire_defaults(model: str, model_kwargs: dict[str, Any] | None, wire_protocol: str) -> dict[str, Any]:
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
    return merged
