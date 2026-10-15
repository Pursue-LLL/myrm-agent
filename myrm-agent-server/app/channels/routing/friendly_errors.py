"""Member-safe error text for channel replies.

Channel members (owner, guests and paired users alike) see one localized sentence per error kind plus a
short reference id; the provider's own wording, endpoints and diagnostic steps never reach the chat. The
reference id is what the operator greps for in the logs.

[INPUT]
- llms.errors.classifier::classify_error, ErrorKind (POS: LLM error classification)
- channels.i18n::channel_t, get_text (POS: Channel i18n message catalog)
- channels.types::InboundMessage (POS: Channel message types)

[OUTPUT]
- friendly_error_text(): ErrorKind → localized sentence with reference id
- friendly_error_message(): Classify exception → friendly_error_text

[POS]
Single source of the user-facing wording for failed channel turns, shared by the router's exception path
and the executor's failed-stream reply.
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error

from app.channels.i18n import channel_t, get_text
from app.channels.types import InboundMessage

_ERROR_KIND_KEYS: dict[ErrorKind, str] = {
    ErrorKind.RATE_LIMIT: "error_rate_limit",
    ErrorKind.OVERLOADED: "error_overloaded",
    ErrorKind.BILLING: "error_billing",
    ErrorKind.AUTH: "error_auth",
    ErrorKind.TIMEOUT: "error_timeout",
    ErrorKind.CONTEXT_OVERFLOW: "error_context_overflow",
    ErrorKind.FORMAT_ERROR: "error_format",
    ErrorKind.MODEL_NOT_FOUND: "error_model_not_found",
    ErrorKind.SAFETY_BLOCK: "error_safety_block",
    ErrorKind.CHALLENGE_BLOCKED: "error_challenge_blocked",
    ErrorKind.RESPONSE_FORMAT_ERROR: "error_response_format",
    ErrorKind.UNKNOWN: "error_unknown",
}
assert set(_ERROR_KIND_KEYS) == set(ErrorKind), f"_ERROR_KIND_KEYS missing: {set(ErrorKind) - set(_ERROR_KIND_KEYS)}"


def _error_ref_id() -> str:
    """Short 8-char hex reference ID for correlating user-facing messages with logs."""
    return uuid.uuid4().hex[:8]


def friendly_error_text(
    kind: ErrorKind,
    msg: InboundMessage | None = None,
    *,
    locale: str | None = None,
) -> tuple[str, str]:
    """Return ``(friendly_message, ref_id)`` for an error of *kind*.

    The friendly message is safe to display in any channel — it never
    contains internal error details. The ref_id links to the full error
    the caller logs at ERROR level.
    """
    ref_id = _error_ref_id()
    catalog_key = _ERROR_KIND_KEYS[kind]
    if msg is not None:
        base = get_text(msg, catalog_key)
    else:
        base = channel_t(locale, catalog_key)
    return f" {base} [ref: {ref_id}]", ref_id


def friendly_error_message(
    exc: Exception,
    msg: InboundMessage | None = None,
    *,
    locale: str | None = None,
) -> tuple[str, str]:
    """Classify *exc* and return ``(friendly_message, ref_id)``."""
    return friendly_error_text(classify_error(exc), msg, locale=locale)
