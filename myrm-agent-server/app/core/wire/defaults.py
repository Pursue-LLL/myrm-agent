"""Default model kwargs for wire-specific model families.

[INPUT]
- myrm_agent_harness.core.config.wire::DEFAULT_WIRE_PROTOCOL (POS: Framework-level SSOT for wire protocol identifiers.)
- myrm_agent_harness.toolkits.llms.core.reasoning_profile::extract_reasoning_effort, is_reasoning_explicitly_disabled, is_reasoning_explicitly_enabled (POS: SSOT for the reasoning level a model kwargs dict states.)

[OUTPUT]
- apply_wire_defaults: merges wire-aware defaults into model_kwargs without overwriting explicit user values

[POS]
Defaults layer of the wire routing: adds the request defaults that the `responses` wire needs for muse-spark models, the
low reasoning effort of MiniMax M3 on MiniMax's own chat endpoint and the gateway headers and provider hint for Vercel AI
Gateway endpoints, while explicit user values always win.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from myrm_agent_harness.core.config.wire import DEFAULT_WIRE_PROTOCOL
from myrm_agent_harness.toolkits.llms.core.reasoning_profile import (
    extract_reasoning_effort,
    is_reasoning_explicitly_disabled,
    is_reasoning_explicitly_enabled,
)

_MUSE_SPARK_PATTERN = re.compile(r"^muse-spark", re.IGNORECASE)
_MINIMAX_M3_PATTERN = re.compile(r"^minimax-m3", re.IGNORECASE)
_MINIMAX_HOSTS = ("minimaxi.com", "minimax.io")

# MiniMax M3 requires adaptive thinking (a request that switches thinking off is rejected with HTTP 400) and takes `low` and
# `minimal` as reasoning effort. `low` is the level checked end to end on tool-heavy agent runs, where it cut the reasoning
# Tokens by 82% to 90% and the model time by 40% to 53% with the same graded answers.
_MINIMAX_M3_EFFORT = "low"


def _states_reasoning_level(model_kwargs: Mapping[str, object]) -> bool:
    """Whether the caller already chose a reasoning level: an effort, a thinking switch or a thinking budget."""
    return (
        extract_reasoning_effort(model_kwargs) is not None
        or is_reasoning_explicitly_enabled(model_kwargs)
        or is_reasoning_explicitly_disabled(model_kwargs)
    )


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

    if (
        wire_protocol == DEFAULT_WIRE_PROTOCOL
        and _MINIMAX_M3_PATTERN.search(normalized)
        and any(host in (base_url or "").lower() for host in _MINIMAX_HOSTS)
        and not _states_reasoning_level(merged)
    ):
        merged["reasoning_effort"] = _MINIMAX_M3_EFFORT

    if provider_id == "vercel_ai_gateway" or (base_url and "ai-gateway.vercel.sh" in base_url):
        raw_headers = merged.get("extra_headers")
        extra_headers = dict(raw_headers) if isinstance(raw_headers, dict) else {}
        extra_headers.setdefault("HTTP-Referer", "https://myrm.ai")
        extra_headers.setdefault("X-Title", "Myrm Agent")
        extra_headers.setdefault("User-Agent", "Myrm/1.0 (Vercel-AI-Gateway-Client)")
        merged["extra_headers"] = extra_headers
        merged.setdefault("custom_llm_provider", "openai")

    return merged
