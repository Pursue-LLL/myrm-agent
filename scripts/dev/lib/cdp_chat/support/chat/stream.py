"""Agent-stream turns over REST.

[INPUT]
- cdp_chat.support.api_client::_e2e_api_urlopen, _set_http_response_read_timeout, get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.timeouts::signoff_parallel_force_chat_timeout_sec (POS: Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers)

[OUTPUT]
- _collect_agent_stream_events: POST agent-stream and collect its SSE; package-internal, shared by the clarify turns
- nudge_agent_stream_turn: follow-up turn over agent-stream

[POS]
Agent-stream turns over REST without a browser: SSE collection of a POST up to a deadline, idle time or terminal event, and the follow-up nudge turn.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

from cdp_chat.support.api_client import (
    _e2e_api_urlopen,
    _set_http_response_read_timeout,
    get_e2e_api_url,
)
from cdp_chat.support.timeouts import signoff_parallel_force_chat_timeout_sec


def _collect_agent_stream_events(
    payload: dict[str, object],
    *,
    api_url: str | None = None,
    timeout_sec: float = 180.0,
    stop_on_clarification: bool = False,
    idle_timeout_sec: float | None = None,
) -> dict[str, object]:
    """POST agent-stream and collect SSE until deadline, idle, or terminal event."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    req = urllib.request.Request(
        f"{resolved}/api/v1/agents/agent-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: list[dict[str, object]] = []
    error_event: dict[str, object] | None = None
    deadline = time.monotonic() + timeout_sec
    resolved_idle_timeout = (
        idle_timeout_sec
        if idle_timeout_sec is not None
        else min(45.0, max(15.0, timeout_sec / 3.0))
    )
    if idle_timeout_sec is None and os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        # Signoff clarify/API legs: parallel wave load can stall SSE >45s between tokens.
        resolved_idle_timeout = signoff_parallel_force_chat_timeout_sec(45.0)
        resolved_idle_timeout = min(
            120.0, max(resolved_idle_timeout, timeout_sec * 0.5)
        )
    last_event_at = time.monotonic()
    connect_timeout_sec = min(30.0, max(5.0, timeout_sec / 3.0))
    clarification_seen = False
    post_clarify_deadline: float | None = None
    try:
        with _e2e_api_urlopen(req, timeout_sec=connect_timeout_sec) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "events": events,
                    "error": {
                        "type": "error",
                        "error_type": "AgentStreamHttpError",
                        "status": status,
                        "body": body[:500],
                    },
                }
            while time.monotonic() < deadline:
                now = time.monotonic()
                skip_idle_break = False
                if not skip_idle_break and now - last_event_at >= resolved_idle_timeout:
                    error_event = {
                        "type": "error",
                        "error_type": "AgentStreamIdleTimeout",
                        "error": (
                            "agent-stream idle timeout "
                            f"after {resolved_idle_timeout:.0f}s without SSE data"
                        ),
                    }
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                _set_http_response_read_timeout(resp, min(30.0, remaining))
                try:
                    line_bytes = resp.readline()
                except TimeoutError:
                    continue
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                events.append(data)
                last_event_at = time.monotonic()
                if data.get("type") == "error":
                    error_event = data
                    break
                if (
                    stop_on_clarification
                    and data.get("type") == "clarification_required"
                ):
                    clarification_seen = True
                    post_clarify_deadline = time.monotonic() + min(
                        15.0,
                        max(5.0, timeout_sec / 6.0),
                    )
                    continue
                if stop_on_clarification and clarification_seen:
                    if raw == "[DONE]" or data.get("type") == "message_end":
                        break
                    if (
                        post_clarify_deadline is not None
                        and time.monotonic() >= post_clarify_deadline
                    ):
                        break
                    continue
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            body = ""
        error_event = {
            "type": "error",
            "error_type": (
                "AgentBusyError" if exc.code in {409, 423} else "AgentStreamHttpError"
            ),
            "status": exc.code,
            "error": f"HTTP Error {exc.code}: {exc.reason}",
            "body": body[:500],
        }
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        error_event = {
            "type": "error",
            "error_type": "AgentStreamConnectTimeout",
            "error": str(exc),
        }

    if stop_on_clarification and error_event is None and not clarification_seen:
        event_types = sorted(
            {
                str(event.get("type"))
                for event in events
                if isinstance(event, dict) and event.get("type") is not None
            }
        )
        error_event = {
            "type": "error",
            "error_type": "AgentStreamClarifyIncomplete",
            "error": (
                "agent-stream ended without clarification_required "
                f"within {timeout_sec:.0f}s"
            ),
            "event_types": event_types,
        }

    return {
        "events": events,
        "error": error_event,
    }


def nudge_agent_stream_turn(
    chat_id: str,
    agent_id: str,
    message: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    """Follow-up turn via agent-stream REST (no Chrome bridge; LIVE empty-write nudge)."""
    normalized_chat = chat_id.strip()
    normalized_agent = agent_id.strip()
    normalized_message = message.strip()
    if not normalized_chat or not normalized_agent or not normalized_message:
        return {"ok": False, "err": "missing-chat-agent-or-message"}
    payload: dict[str, object] = {
        "messageId": f"e2e-nudge-{uuid.uuid4().hex[:10]}",
        "chatId": normalized_chat,
        "query": normalized_message,
        "actionMode": "agent",
        "agentId": normalized_agent,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    result = _collect_agent_stream_events(
        payload,
        api_url=api_url,
        timeout_sec=timeout_sec,
    )
    error = result.get("error")
    if isinstance(error, dict):
        return {
            "ok": False,
            "mode": "agentStreamNudge",
            "error": error,
            "events": result.get("events"),
        }
    return {"ok": True, "mode": "agentStreamNudge", "events": result.get("events", [])}
