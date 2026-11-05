"""Splitting one call's keyword arguments into transport options and request-body parameters.

[INPUT]
- (none) Pure dict transforms.

[OUTPUT]
- CallOptions: the transport-level options of a call and its remaining body parameters
- split_params: separate credentials / timeout / proxy / headers / extra_body from the body parameters
- wants_answer_cache: whether the caller left the call in the answer cache (``answer_cache=False`` opts out)
- merge_headers: case-insensitive header overlay shared by every wire

[POS]
Every wire module starts from the same keyword arguments the adapter hands over (model, endpoint, credential,
timeout, proxy, headers, ``extra_body``, the ``answer_cache`` switch and the OpenAI-shaped generation parameters).
This module is the single place that decides which of them are transport concerns and which belong in the
provider's request body, so no wire re-implements the split.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

ANSWER_CACHE: Final = "answer_cache"

_TRANSPORT_KEYS: Final = frozenset(
    {
        "model",
        "messages",
        "api_base",
        "base_url",
        "api_key",
        "custom_llm_provider",
        "timeout",
        "proxy",
        "extra_headers",
        "extra_body",
        "api_version",
        "organization",
        ANSWER_CACHE,
    }
)


@dataclass(frozen=True, slots=True)
class CallOptions:
    """Transport-level view of one call."""

    timeout: float | None
    proxy: str | None
    headers: dict[str, str]
    extra_body: dict[str, object]
    api_version: str | None
    organization: str | None
    stream: bool
    body: dict[str, object] = field(default_factory=dict)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): str(v) for k, v in value.items() if v is not None}


def _object_map(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, Mapping) else {}


def split_params(params: Mapping[str, object]) -> CallOptions:
    """Split ``params``; ``None`` values never reach the wire."""
    timeout = params.get("timeout")
    return CallOptions(
        timeout=float(timeout) if isinstance(timeout, (int, float)) else None,
        proxy=_text(params.get("proxy")),
        headers=_string_map(params.get("extra_headers")),
        extra_body=_object_map(params.get("extra_body")),
        api_version=_text(params.get("api_version")),
        organization=_text(params.get("organization")),
        stream=params.get("stream") is True,
        body={k: v for k, v in params.items() if k not in _TRANSPORT_KEYS and v is not None},
    )


def wants_answer_cache(params: Mapping[str, object]) -> bool:
    """Only an explicit ``answer_cache=False`` opts a call out; the call then neither reads nor files an answer."""
    return params.get(ANSWER_CACHE) is not False


def merge_headers(base: Mapping[str, str], extra: Mapping[str, str]) -> dict[str, str]:
    """``extra`` over ``base`` with case-insensitive names; the caller's casing wins."""
    lowered = {k.lower() for k in extra}
    merged = {k: v for k, v in base.items() if k.lower() not in lowered}
    merged.update(extra)
    return merged
