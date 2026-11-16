"""Browser takeover over the REST API.

[INPUT]
- cdp_chat.support.api_client::_e2e_api_get_json, _e2e_api_post_json, get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.chat.session::fetch_chat_messages (POS: Chat session calls of the E2E over the REST API: create, cancel, read messages, steer)

[OUTPUT]
- chat_browser_gate_from_api: REST mirror of the browser tool progress
- fetch_pending_browser_takeover_resume, fetch_browser_takeover_resume_ids: the chat and message ids a takeover resumes with
- deny_stale_browser_takeover_approvals: deny orphan pending takeover approvals

[POS]
Browser takeover state over the REST API: tool progress when mux probes are degraded, the ids a pending takeover resumes with, denial of stale approvals.
"""

from __future__ import annotations

import urllib.error

from cdp_chat.support.api_client import (
    _e2e_api_get_json,
    _e2e_api_post_json,
    get_e2e_api_url,
)
from cdp_chat.support.chat.session import fetch_chat_messages


def chat_browser_gate_from_api(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
) -> dict[str, object]:
    """REST mirror of E2E ``getBrowserToolProgress`` when MUX probes are degraded."""
    normalized = chat_id.strip()
    if not normalized:
        return {"lastTool": "", "takeoverPending": False, "fromApi": True}
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    last_tool = ""
    messages = fetch_chat_messages(
        normalized, api_url=resolved_api, timeout_sec=timeout_sec
    )
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        steps = msg.get("progressSteps") or msg.get("progress_steps") or []
        if not isinstance(steps, list):
            continue
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool_name") or step.get("toolName") or "")
            if tool_name.startswith("browser_"):
                last_tool = tool_name
                break
        if last_tool:
            break
    # `lastTool` is display-only context. The tool *name* proves nothing: a call that
    # raised still lands in progressSteps. `takeoverPending` must come from the approval
    # ledger, which only records a row when the turn actually parked on the interrupt.
    takeover_pending = False
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/approvals?limit=50&offset=0",
            timeout_sec=10.0,
        )
        records = payload.get("approvals") if isinstance(payload, dict) else None
        if isinstance(records, list):
            for raw in records:
                if not isinstance(raw, dict):
                    continue
                if (
                    raw.get("action_type") == "browser_takeover"
                    and raw.get("status") == "PENDING"
                    and str(raw.get("chat_id") or "") == normalized
                ):
                    takeover_pending = True
                    if not last_tool:
                        last_tool = "browser_ask_human_tool"
                    break
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        pass
    return {
        "lastTool": last_tool,
        "takeoverPending": takeover_pending,
        "fromApi": True,
    }


def fetch_pending_browser_takeover_resume(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, str] | None:
    """Return chat/message ids for a pending browser_takeover approval (REST-only)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/approvals?limit=50&offset=0",
            timeout_sec=15.0,
        )
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        return None
    records = payload.get("approvals") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return None
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("action_type") != "browser_takeover"
            or raw.get("status") != "PENDING"
            or str(raw.get("chat_id") or "") != normalized
        ):
            continue
        nested = raw.get("payload")
        message_id = ""
        if isinstance(nested, dict):
            message_id = str(
                nested.get("messageId") or nested.get("message_id") or ""
            ).strip()
        if not message_id:
            message_id = str(raw.get("message_id") or "").strip()
        if message_id:
            return {"chatId": normalized, "resumeMessageId": message_id}
    return None


def _resume_message_id_from_chat_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> str | None:
    """Resolve HITL resume messageId from persisted chat messages (yolo / no approval row)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    messages = fetch_chat_messages(normalized, api_url=api_url)
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        steps: object = msg.get("progressSteps") or msg.get("progress_steps")
        if not isinstance(steps, list):
            meta = msg.get("metadata")
            if isinstance(meta, dict):
                steps = meta.get("progressSteps") or meta.get("progress_steps")
        has_takeover = False
        if isinstance(steps, list):
            for step in reversed(steps):
                if not isinstance(step, dict):
                    continue
                tool_name = str(step.get("tool_name") or step.get("toolName") or "")
                if not tool_name.endswith("browser_ask_human_tool"):
                    continue
                has_takeover = True
                step_mid = str(
                    step.get("messageId") or step.get("message_id") or ""
                ).strip()
                if step_mid:
                    return step_mid
                break
        if has_takeover or msg.get("loading") is True:
            message_id = str(
                msg.get("messageId") or msg.get("message_id") or msg.get("id") or ""
            ).strip()
            if message_id:
                return message_id
    return None


def fetch_browser_takeover_resume_ids(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, str] | None:
    """Return chat/message ids for browser takeover resume (approvals → chat messages)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    ids = fetch_pending_browser_takeover_resume(normalized, api_url=api_url)
    if ids:
        return ids
    message_id = _resume_message_id_from_chat_messages(normalized, api_url=api_url)
    if message_id:
        return {"chatId": normalized, "resumeMessageId": message_id}
    return None


def deny_stale_browser_takeover_approvals(*, api_url: str | None = None) -> int:
    """Deny orphan PENDING browser_takeover approvals before LIVE Chrome E2E."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    denied = 0
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/approvals?limit=50&offset=0",
            timeout_sec=15.0,
        )
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        return 0
    records = payload.get("approvals") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("action_type") != "browser_takeover"
            or raw.get("status") != "PENDING"
        ):
            continue
        approval_id = str(raw.get("id") or raw.get("approval_id") or "").strip()
        if not approval_id:
            continue
        try:
            _e2e_api_post_json(
                f"{resolved_api}/api/v1/approvals/{approval_id}/resolve",
                {"decision": "deny"},
                timeout_sec=15.0,
            )
            denied += 1
        except (OSError, TimeoutError, urllib.error.URLError, ValueError):
            continue
    return denied
