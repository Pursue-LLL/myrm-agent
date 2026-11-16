"""Clarification turns over the API.

[INPUT]
- cdp_chat.support.chat.evidence::stored_reply_matches (POS: What the stored chat messages prove about a turn: a real file-write tool call, an OK or DONE reply in the newest assistant message, the user message count)
- cdp_chat.support.chat.session::fetch_chat_messages (POS: Chat session calls of the E2E over the REST API: create, cancel, read messages, steer)
- cdp_chat.support.chat.stream::_collect_agent_stream_events (POS: Agent-stream turns over REST without a browser: SSE collection of a POST up to a deadline, idle time or terminal event, and the follow-up nudge turn)
- cdp_chat.clarify_skip::continued_after_skip, open_clarification, pending_clarification_interrupt_id, skip_resume_value, sse_message_text (POS: measurement ruler of the clarify Skip E2E: a skip is judged by evidence of continuation)

[OUTPUT]
- start_clarify_turn_via_api, resume_clarify_skip_via_api: reach the clarification card, skip it
- is_hitl_already_resolved, clarify_skip_resume_should_retry: whether a skip resume is final or worth a retry
- chat_has_pending_clarification, chat_pending_clarification_interrupt_id, chat_messages_have_clarify_skip_done: what the stored messages show of the card and the skip

[POS]
Clarification turns over the API: start a turn until it asks, skip the open card, and judge from stored messages whether a card is pending and the skip reached the agent.
"""

from __future__ import annotations

import re
import urllib.error
import uuid

from cdp_chat.clarify_skip import (
    continued_after_skip,
    open_clarification,
    pending_clarification_interrupt_id,
    skip_resume_value,
    sse_message_text,
)
from cdp_chat.support.chat.evidence import stored_reply_matches
from cdp_chat.support.chat.session import fetch_chat_messages
from cdp_chat.support.chat.stream import _collect_agent_stream_events

_CLARIFY_SKIP_DONE_RE = re.compile(
    r"DONE-SKIPPED|Clarification answered|已回答澄清",
    re.IGNORECASE,
)


def start_clarify_turn_via_api(
    chat_id: str,
    *,
    query: str,
    model_selection: dict[str, object],
    api_url: str | None = None,
    timeout_sec: float = 120.0,
) -> dict[str, object]:
    """POST agent-stream until clarification_required (API fallback for LIVE clarify E2E)."""
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": str(query),
        "modelSelection": model_selection,
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["structured_clarify"]},
    }
    collected = _collect_agent_stream_events(
        payload,
        api_url=api_url,
        timeout_sec=timeout_sec,
        stop_on_clarification=True,
    )
    events = collected.get("events")
    error_event = collected.get("error")
    if not isinstance(events, list):
        events = []
    has_clarification = any(
        isinstance(event, dict) and event.get("type") == "clarification_required"
        for event in events
    )
    event_types = sorted(
        {
            str(event.get("type"))
            for event in events
            if isinstance(event, dict) and event.get("type") is not None
        }
    )
    return {
        "ok": error_event is None and has_clarification,
        "has_clarification": has_clarification,
        "events": events,
        "event_types": event_types,
        "error": error_event,
    }


def resume_clarify_skip_via_api(
    chat_id: str,
    *,
    interrupt_id: str,
    model_selection: dict[str, object],
    api_url: str | None = None,
    timeout_sec: float = 180.0,
    query: str = "",
) -> dict[str, object]:
    """Skip the open card the way its Skip button does (a resume addressed to ``interrupt_id``).

    ``ok`` needs evidence that the agent continued; the stream merely ending proves nothing.
    """
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": str(query),
        "modelSelection": model_selection,
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["structured_clarify"]},
        "resumeValue": skip_resume_value(interrupt_id),
    }
    collected = _collect_agent_stream_events(
        payload,
        api_url=api_url,
        timeout_sec=timeout_sec,
        stop_on_clarification=False,
    )
    events = collected.get("events")
    error_event = collected.get("error")
    if not isinstance(events, list):
        events = []

    final_text = sse_message_text(events)
    event_types = sorted(
        {
            str(event.get("type"))
            for event in events
            if isinstance(event, dict) and event.get("type") is not None
        }
    )
    return {
        "ok": error_event is None and continued_after_skip(events),
        "events": events,
        "event_types": event_types,
        "final_text": final_text,
        "error": error_event,
    }


def is_hitl_already_resolved(result: dict[str, object]) -> bool:
    """True when resume/skip hit an interrupt the timeout or another client already resolved (409, non-retryable)."""
    error = result.get("error")
    if not isinstance(error, dict):
        return False
    if error.get("error_type") != "AgentBusyError":
        return False
    fragments: list[str] = []
    for key in ("error", "body", "detail"):
        raw = error.get(key)
        if raw is not None:
            fragments.append(str(raw))
    return "already been resolved" in " ".join(fragments).lower()


def clarify_skip_resume_should_retry(result: dict[str, object]) -> bool:
    """True when SSE ended early (e.g. UI stream still holds agent) and retry may succeed."""
    if result.get("ok") is True:
        return False
    if is_hitl_already_resolved(result):
        return False
    error = result.get("error")
    if isinstance(error, dict) and error.get("error_type") in {
        "AgentBusyError",
        "AgentStreamClarifyIncomplete",
        "AgentStreamIdleTimeout",
    }:
        return True
    events = result.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("error_type") == "AgentBusyError":
                return True
            if (
                event.get("type") == "error"
                and event.get("error_type") == "AgentBusyError"
            ):
                return True
    event_types = result.get("event_types")
    if not isinstance(event_types, list):
        return False
    normalized = {str(item) for item in event_types}
    if normalized == {"progress"}:
        return True
    return normalized == {"error"}


def _stored_messages_or_empty(
    chat_id: str, *, api_url: str | None
) -> list[dict[str, object]]:
    """Stored chat messages; an empty chat id or a stalled backend reads as no messages (not-ready)."""
    normalized = chat_id.strip()
    if not normalized:
        return []
    try:
        return fetch_chat_messages(normalized, api_url=api_url)
    except (TimeoutError, OSError, urllib.error.URLError):
        # SHPOIB/shared backend may stall under parallel LIVE load; treat as not-ready.
        return []


def chat_has_pending_clarification(chat_id: str, *, api_url: str | None = None) -> bool:
    """Return True when chat messages show unanswered structured clarify (API SSOT)."""
    return (
        open_clarification(_stored_messages_or_empty(chat_id, api_url=api_url))
        is not None
    )


def chat_pending_clarification_interrupt_id(
    chat_id: str, *, api_url: str | None = None
) -> str | None:
    """The pause the open clarification card waits on; None when no card is open or it was stored without an id."""
    return pending_clarification_interrupt_id(
        _stored_messages_or_empty(chat_id, api_url=api_url)
    )


def chat_messages_have_clarify_skip_done(
    chat_id: str, *, min_user_count: int = 1, api_url: str | None = None
) -> bool:
    """Return True when the last assistant message shows clarify Skip resume completed."""
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    return stored_reply_matches(
        messages, _CLARIFY_SKIP_DONE_RE, min_user_count=min_user_count
    )
