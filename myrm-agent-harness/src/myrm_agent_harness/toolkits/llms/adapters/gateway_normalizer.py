"""OpenAI compatible gateway normalization and 400 parameter downgrade handler.

Provides adaptive parameter sanitization for non-standard or lightweight OpenAI
proxies (OneAPI, Ollama, SiliconFlow, vLLM, etc.) when they reject non-standard
or optional parameters with HTTP 400.

[INPUT]
- Exception/error objects, params dict

[OUTPUT]
- sanitize_gateway_params_on_400(): Adaptive parameter stripping on HTTP 400 format errors; a rejected parameter
  leaves both the top level and ``extra_body``, and a rejected reasoning control is remembered per endpoint and value
- is_gateway_param_rejection(): Check whether 400 error is due to an unsupported parameter
- drop_rejected_reasoning_params(): Removes the reasoning controls an endpoint already rejected from a request

[POS]
OpenAI-compatible gateway normalizer. Downgrades a request the gateway rejected with HTTP 400 and remembers
the rejection per endpoint, so the same request does not fail again.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Final

logger = logging.getLogger(__name__)

# Patterns matching parameter rejections in 400 Bad Request error messages
_PARAM_REJECTION_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(
            r"stream_options|unknown field.*stream_options|unsupported.*stream_options",
            re.IGNORECASE,
        ),
        ("stream_options",),
    ),
    (
        re.compile(
            r"parallel_tool_calls|unknown field.*parallel_tool_calls|unsupported.*parallel_tool_calls",
            re.IGNORECASE,
        ),
        ("parallel_tool_calls",),
    ),
    (
        re.compile(
            r"reasoning_effort|unknown field.*reasoning_effort|unsupported.*reasoning_effort",
            re.IGNORECASE,
        ),
        ("reasoning_effort",),
    ),
    (
        re.compile(
            r"unrecognized request argument[^.]{0,40}thinking"
            r"|(?:unknown|unsupported|unexpected|extra)[^.]{0,40}\bthinking\b"
            r"|\bthinking\b[^.]{0,40}(?:not supported|unsupported|not allowed|not permitted|unknown)",
            re.IGNORECASE,
        ),
        ("thinking",),
    ),
    (
        re.compile(r"presence_penalty|frequency_penalty", re.IGNORECASE),
        ("presence_penalty", "frequency_penalty"),
    ),
    (
        re.compile(
            r"max_completion_tokens|unknown field.*max_completion_tokens|unsupported.*max_completion_tokens",
            re.IGNORECASE,
        ),
        ("max_completion_tokens",),
    ),
    (
        re.compile(
            r"temperature.*(?:not supported|unsupported|does not support|deprecated)|unsupported.*temperature",
            re.IGNORECASE,
        ),
        ("temperature",),
    ),
    (
        re.compile(
            r"response_format|unknown field.*response_format|unsupported.*response_format"
            r"|output_format|structured outputs?[^.]{0,40}(?:not supported|unsupported)",
            re.IGNORECASE,
        ),
        ("response_format",),
    ),
    (
        re.compile(
            r"unknown field.*['\"]?user['\"]?|unsupported.*['\"]?user['\"]?",
            re.IGNORECASE,
        ),
        ("user",),
    ),
    (
        re.compile(
            r"top_p.*(?:not supported|unsupported|does not support|deprecated)|unsupported.*top_p"
            r"|temperature.*top_p|top_p.*temperature",
            re.IGNORECASE,
        ),
        ("top_p",),
    ),
    (
        re.compile(
            r"top_k.*(?:not supported|unsupported|does not support|deprecated)|unsupported.*top_k", re.IGNORECASE
        ),
        ("top_k",),
    ),
)

# Structured-output rejections that never name our parameter. Strict gateways and
# grammar backends reject the schema shape itself: a bare {"type": "object"} node
# without properties, or a grammar the backend cannot compile. These wordings carry
# no parameter token, so the name-based table above cannot match them.
_STRUCTURED_OUTPUT_SCHEMA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"an object with no properties is not allowed", re.IGNORECASE),
    re.compile(r"guided_grammar|xgrammar|compile_grammar_error", re.IGNORECASE),
)

# Schema name of the internally injected constrained tool-call transport. Only this
# transport is ever auto-stripped on schema-shape rejections; a user-supplied
# response_format is left untouched so explicit structured output keeps working.
_TOOL_CALLS_TRANSPORT_SCHEMA_NAME = "tool_calls_transport"

# Endpoints whose internal tool-call transport was rejected once, keyed by
# (model, base_url). Bounded process-local memory so a mis-detected endpoint pays
# exactly one failed request; endpoint or model changes alter the key.
_TRANSPORT_STRIP_MEMO: dict[tuple[str, str], None] = {}

# Bound shared by the process-local endpoint memories of this module.
_MEMO_CAP: Final = 256

# Reasoning controls an endpoint rejected: (model, base_url, param, value) -> expiry. Dropping one costs the caller's
# intent, so the memory expires (a provider may add support) and carries the value: a level the endpoint rejected
# does not block a level it accepts.
_REASONING_PARAMS: Final = ("reasoning_effort", "thinking")
_REJECTED_REASONING: dict[tuple[str, str, str, str], float] = {}
_REJECTED_REASONING_TTL_S: Final = 3600.0


def _normalize_memo_key(model: str, base_url: str) -> tuple[str, str]:
    """Normalize endpoint identity for the endpoint memories."""
    return (model or "").strip().lower(), (base_url or "").strip().lower()


def is_transport_stripped(model: str = "", base_url: str = "") -> bool:
    """Return True when this endpoint already rejected the internal tool-call transport."""
    return _normalize_memo_key(model, base_url) in _TRANSPORT_STRIP_MEMO


def remember_stripped_transport(model: str = "", base_url: str = "") -> None:
    """Record that an endpoint rejected the internal tool-call transport."""
    key = _normalize_memo_key(model, base_url)
    if key == ("", "") or key in _TRANSPORT_STRIP_MEMO:
        return
    if len(_TRANSPORT_STRIP_MEMO) >= _MEMO_CAP:
        _TRANSPORT_STRIP_MEMO.pop(next(iter(_TRANSPORT_STRIP_MEMO)))
    _TRANSPORT_STRIP_MEMO[key] = None


def _param_value(params: dict[str, object], key: str) -> object:
    """The value of ``key`` in the request params, from the top level or ``extra_body``."""
    if key in params:
        return params[key]
    extra_body = params.get("extra_body")
    return extra_body.get(key) if isinstance(extra_body, dict) else None


def _strip_param(params: dict[str, object], key: str) -> bool:
    """Remove ``key`` from the top level and from ``extra_body``; True when either held it.

    The model factory mirrors body fields into ``extra_body``, so a field left there would ride into the retry.
    The mirror is replaced rather than edited: that dict is shared with the model configuration.
    """
    present = key in params
    params.pop(key, None)
    extra_body = params.get("extra_body")
    if isinstance(extra_body, dict) and key in extra_body:
        params["extra_body"] = {name: value for name, value in extra_body.items() if name != key}
        present = True
    return present


def _reasoning_key(model: str, base_url: str, param: str, value: object) -> tuple[str, str, str, str]:
    return (*_normalize_memo_key(model, base_url), param, repr(value))


def _remember_rejected_reasoning(model: str, base_url: str, param: str, value: object) -> None:
    """Record that an endpoint rejected one reasoning control value."""
    if value is None:
        return
    key = _reasoning_key(model, base_url, param, value)
    if key not in _REJECTED_REASONING and len(_REJECTED_REASONING) >= _MEMO_CAP:
        _REJECTED_REASONING.pop(next(iter(_REJECTED_REASONING)))
    _REJECTED_REASONING[key] = time.monotonic() + _REJECTED_REASONING_TTL_S


def drop_rejected_reasoning_params(params: dict[str, object], *, model: str, base_url: str) -> None:
    """Remove the reasoning controls this endpoint already rejected, so a request does not fail the same way again."""
    if not _REJECTED_REASONING:
        return
    now = time.monotonic()
    for param in _REASONING_PARAMS:
        value = _param_value(params, param)
        if value is None:
            continue
        key = _reasoning_key(model, base_url, param, value)
        expiry = _REJECTED_REASONING.get(key)
        if expiry is None:
            continue
        if expiry <= now:
            del _REJECTED_REASONING[key]
        else:
            _strip_param(params, param)


def _response_format_is_internal_transport(value: object) -> bool:
    """Return True when a response_format value is our injected tool-call transport."""
    if not isinstance(value, dict):
        return False
    json_schema = value.get("json_schema")
    return isinstance(json_schema, dict) and json_schema.get("name") == _TOOL_CALLS_TRANSPORT_SCHEMA_NAME


def _strip_internal_tool_calls_transport(params: dict[str, Any]) -> bool:
    """Remove our injected tool-call transport (top-level and extra_body)."""
    removed = False
    if _response_format_is_internal_transport(params.get("response_format")):
        params.pop("response_format", None)
        removed = True
    extra_body = params.get("extra_body")
    if isinstance(extra_body, dict) and _response_format_is_internal_transport(extra_body.get("response_format")):
        extra_body.pop("response_format", None)
        removed = True
    return removed


def is_gateway_param_rejection(exc: Exception) -> bool:
    """Return True if the exception indicates a gateway 400 error caused by an unsupported parameter."""
    err_str = str(exc).lower()
    for pattern, _ in _PARAM_REJECTION_PATTERNS:
        if pattern.search(err_str):
            return True
    return any(pattern.search(err_str) for pattern in _STRUCTURED_OUTPUT_SCHEMA_PATTERNS)


def sanitize_gateway_params_on_400(
    params: dict[str, Any],
    exc: Exception,
    *,
    model: str = "",
    base_url: str = "",
) -> list[str]:
    """Inspect the 400 error and strip the rejected parameters from params.

    For parameters with fallback compatibility (e.g. max_completion_tokens -> max_tokens),
    automatically maps the value to the compatible parameter key. Schema-shape rejections
    strip only our internally injected tool-call transport; user-supplied response_format
    is preserved. Whenever our internal transport is stripped, the endpoint is remembered
    so future requests skip the injection and never pay the failed call.

    Returns the list of parameter names that were stripped.
    """
    err_str = str(exc).lower()
    stripped: list[str] = []

    # Preserve value before stripping for fallback mappings
    saved_max_completion_tokens = params.get("max_completion_tokens")

    # Snapshot before stripping: a name-based rejection of our internal transport
    # qualifies for endpoint memory too, so mis-detected endpoints pay one retry.
    had_internal_transport = _response_format_is_internal_transport(params.get("response_format")) or (
        isinstance(params.get("extra_body"), dict)
        and _response_format_is_internal_transport(params["extra_body"].get("response_format"))
    )

    for pattern, param_keys in _PARAM_REJECTION_PATTERNS:
        if pattern.search(err_str):
            for key in param_keys:
                if key in stripped:
                    continue
                rejected_value = _param_value(params, key)
                if _strip_param(params, key):
                    stripped.append(key)
                    if key in _REASONING_PARAMS:
                        _remember_rejected_reasoning(model, base_url, key, rejected_value)

    for pattern in _STRUCTURED_OUTPUT_SCHEMA_PATTERNS:
        if pattern.search(err_str):
            if _strip_internal_tool_calls_transport(params) and "response_format" not in stripped:
                stripped.append("response_format")
            break

    if "response_format" in stripped and had_internal_transport:
        remember_stripped_transport(model, base_url)

    # Automatic fallback mapping: max_completion_tokens -> max_tokens
    if "max_completion_tokens" in stripped and saved_max_completion_tokens is not None and "max_tokens" not in params:
        params["max_tokens"] = saved_max_completion_tokens

    if stripped:
        logger.warning(
            " Gateway 400 detected, automatically stripped rejected param(s): %s",
            stripped,
        )

    return stripped
