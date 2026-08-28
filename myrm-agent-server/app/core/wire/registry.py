"""Global model → wire protocol routing (business layer SSOT)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from myrm_agent_harness.core.config.wire import DEFAULT_WIRE_PROTOCOL, WireProtocol

_MUSE_SPARK_PATTERN = re.compile(r"^muse-spark", re.IGNORECASE)
_GPT_PATTERN = re.compile(r"^gpt-", re.IGNORECASE)
_GROK_PATTERN = re.compile(r"^grok-", re.IGNORECASE)
_MINIMAX_PATTERN = re.compile(r"^minimax-", re.IGNORECASE)
_QWEN_PATTERN = re.compile(r"^qwen", re.IGNORECASE)

_OPENCODE_GO_PROVIDER_ID = "opencode_go"


@dataclass(frozen=True, slots=True)
class WireRouteRule:
    pattern: re.Pattern[str]
    wire_protocol: WireProtocol


@dataclass(frozen=True, slots=True)
class WireEndpointContext:
    """Resolve-time endpoint identity for OpenCode wire gating."""

    base_url: str | None = None
    provider_id: str | None = None

    def is_opencode_scoped(self) -> bool:
        if self.provider_id == _OPENCODE_GO_PROVIDER_ID:
            return True
        return _is_opencode_endpoint(self.base_url)


_WIRE_RULES: tuple[WireRouteRule, ...] = (
    WireRouteRule(_MUSE_SPARK_PATTERN, "responses"),
    WireRouteRule(_GPT_PATTERN, "responses"),
    WireRouteRule(_GROK_PATTERN, "responses"),
    WireRouteRule(_MINIMAX_PATTERN, "anthropic_messages"),
    WireRouteRule(_QWEN_PATTERN, "anthropic_messages"),
)


def _is_opencode_endpoint(base_url: str | None) -> bool:
    """Wire routing applies to OpenCode Go/Zen HTTP endpoints and local relay."""
    if not base_url:
        return False
    normalized = base_url.strip().lower()
    return "opencode.ai" in normalized or "localhost:20128" in normalized


def normalize_model_name_for_wire(model: str) -> str:
    """Strip LiteLLM provider prefix and muse-spark -free suffix."""
    name = model.strip()
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if name.endswith("-free") and "muse-spark" in name.lower():
        name = name[: -len("-free")]
    return name


def resolve_wire_protocol(
    model: str,
    base_url: str | None = None,
    *,
    provider_id: str | None = None,
) -> WireProtocol:
    """Resolve wire transport from model patterns on OpenCode-scoped endpoints only."""
    endpoint = WireEndpointContext(base_url=base_url, provider_id=provider_id)
    if not endpoint.is_opencode_scoped():
        return DEFAULT_WIRE_PROTOCOL
    normalized = normalize_model_name_for_wire(model)
    for rule in _WIRE_RULES:
        if rule.pattern.search(normalized):
            return rule.wire_protocol
    return DEFAULT_WIRE_PROTOCOL
