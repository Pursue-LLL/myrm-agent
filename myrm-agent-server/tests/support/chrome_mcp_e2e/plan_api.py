"""Dynamic-workflow plan and stream state read and confirmed through the HTTP API."""

from __future__ import annotations

import time

from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from .api import http_json

_GET_STREAM_REQUEST_MESSAGE_ID_JS = """(() => {
  const id = window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.streamRequestMessageId;
  return typeof id === 'string' && id.trim() ? id.trim() : null;
})()"""


def _plan_confirm_response_resolved(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("code")
    if code == 404:
        return False
    if code not in (None, 0, 200):
        return False
    data = payload.get("data")
    return isinstance(data, dict) and data.get("status") == "resolved"


def _post_plan_confirm_via_api(api_base: str, stream_message_id: str) -> bool:
    normalized = stream_message_id.strip()
    if not normalized:
        return False
    try:
        payload = http_json(
            "POST",
            f"{api_base.rstrip('/')}/api/v1/agents/plan-confirm-response",
            {"messageId": normalized, "action": "confirm"},
        )
    except (RuntimeError, OSError, ValueError):
        return False
    return _plan_confirm_response_resolved(payload)


def _resolve_dw_stream_message_id(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    cached: str | None = None,
) -> str | None:
    if isinstance(cached, str) and cached.strip():
        return cached.strip()
    try:
        raw = client.evaluate(
            page,
            _GET_STREAM_REQUEST_MESSAGE_ID_JS,
            timeout_sec=10.0,
        )
    except (RuntimeError, TimeoutError, OSError):
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _plan_confirm_state_from_messages(
    messages: list[dict[str, object]],
) -> dict[str, object]:
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        metadata = msg.get("metadata")
        meta = metadata if isinstance(metadata, dict) else {}
        plan_raw = meta.get("planConfirmation")
        if not isinstance(plan_raw, dict):
            continue
        status = str(plan_raw.get("status") or "")
        if status == "waiting":
            return {"phase": "waiting", "planConfirmation": plan_raw}
        if status in {"confirmed", "edited"}:
            return {"phase": "resolved", "planConfirmation": plan_raw}
    return {"phase": "none"}


def _dw_unattended_enabled(api_base: str) -> bool:
    """True when YOLO or plan_confirm disabled — DW skips plan_confirm HITL."""
    try:
        payload = http_json("GET", f"{api_base.rstrip('/')}/api/v1/config/securityConfig")
    except (RuntimeError, OSError, ValueError):
        return False
    raw = payload.get("value") if isinstance(payload, dict) else payload
    if not isinstance(raw, dict):
        return False
    yolo_enabled = bool(raw.get("yoloModeEnabled") or raw.get("yolo_mode_enabled"))
    plan_confirm_enabled = bool(
        raw.get("planConfirmEnabled") if raw.get("planConfirmEnabled") is not None else raw.get("plan_confirm_enabled", True)
    )
    return yolo_enabled or not plan_confirm_enabled


def _wait_for_yolo_dw_plan_skip(
    *,
    api_base: str,
    chat_id: str,
    timeout_sec: float,
) -> dict[str, object]:
    """YOLO/unattended DW has no plan_confirm card — wait for assistant stream start."""
    normalized_chat_id = chat_id.strip()
    if not normalized_chat_id:
        raise ValueError("chat_id is required for YOLO DW plan skip wait")
    base = api_base.rstrip("/")
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    terminal_statuses = {"complete", "success", "error", "cancelled", "budget_blocked"}
    while time.monotonic() < deadline:
        touch_wall_progress(current_node="workflow_plan_yolo_skip_wait")
        try:
            payload = http_json(
                "GET",
                f"{base}/api/v1/chats/{normalized_chat_id}/messages",
            )
        except (RuntimeError, OSError, ValueError) as exc:
            last = {"ready": False, "err": str(exc)}
            time.sleep(0.25)
            continue
        messages = _messages_from_api_payload(payload)
        plan_state = _plan_confirm_state_from_messages(messages)
        if plan_state.get("phase") == "waiting":
            break
        stream_probe = _api_stream_probe_from_messages(messages)
        last = stream_probe
        sample = str(stream_probe.get("sample") or "")
        completion_status = str(stream_probe.get("completionStatus") or "")
        user_count = int(stream_probe.get("userCount") or 0)
        if user_count >= 1 and (completion_status in terminal_statuses or len(sample.strip()) >= 15):
            return {
                "ready": True,
                "confirmedVia": "yolo_skip",
                "streamProbe": stream_probe,
            }
        time.sleep(0.25)
    raise AssertionError(f"YOLO DW stream did not start within {timeout_sec}s for chat {normalized_chat_id}: {last}")


def _messages_from_api_payload(payload: object) -> list[dict[str, object]]:
    raw: list[object]
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            raw = data["messages"]
        elif isinstance(payload.get("messages"), list):
            raw = payload["messages"]
        else:
            raw = []
    else:
        raw = []
    return [msg for msg in raw if isinstance(msg, dict)]


def _assistant_text_from_api_message(msg: dict[str, object]) -> str:
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _api_stream_probe_from_messages(
    messages: list[dict[str, object]],
) -> dict[str, object]:
    user_count = sum(1 for msg in messages if msg.get("role") == "user")
    last_assistant: dict[str, object] | None = None
    for msg in messages:
        if msg.get("role") == "assistant":
            last_assistant = msg
    if last_assistant is None:
        return {
            "ready": False,
            "userCount": user_count,
            "isStreaming": user_count > 0,
            "sample": "",
            "messageId": None,
        }
    metadata = last_assistant.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    completion_status = str(meta.get("completionStatus") or "")
    is_complete = completion_status in {
        "complete",
        "error",
        "cancelled",
        "success",
        "budget_blocked",
    }
    sample = _assistant_text_from_api_message(last_assistant)
    message_id_raw = last_assistant.get("messageId") or last_assistant.get("id")
    message_id = message_id_raw if isinstance(message_id_raw, str) else None
    is_streaming = user_count > 0 and not is_complete
    ready = user_count >= 1 and not is_streaming and (is_complete or len(sample.strip()) >= 10)
    return {
        "ready": ready,
        "userCount": user_count,
        "isStreaming": is_streaming,
        "sample": sample[:240],
        "messageId": message_id,
        "completionStatus": completion_status,
    }


def wait_for_dw_stream_done_via_api(
    *,
    api_base: str,
    chat_id: str,
    timeout_sec: float = 480.0,
    min_assistant_chars: int = 10,
) -> dict[str, object]:
    """Poll chat messages REST when UI turnSnapshot is blank under parallel SHARED load."""
    normalized_chat_id = chat_id.strip()
    if not normalized_chat_id:
        raise ValueError("chat_id is required for API stream wait")
    base = api_base.rstrip("/")
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    last_touch = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now - last_touch >= 5.0:
            touch_wall_progress(current_node="wait_for_dw_stream_done_via_api")
            last_touch = now
        try:
            payload = http_json(
                "GET",
                f"{base}/api/v1/chats/{normalized_chat_id}/messages",
            )
        except (RuntimeError, OSError, ValueError) as exc:
            last = {"ready": False, "err": str(exc)}
            time.sleep(2.0)
            continue
        messages = _messages_from_api_payload(payload)
        last = _api_stream_probe_from_messages(messages)
        sample = str(last.get("sample") or "")
        completion_status = str(last.get("completionStatus") or "")
        if "orchestration was not approved" in sample.lower() or completion_status == "cancelled":
            raise AssertionError(f"Dynamic Workflow stream failed — orchestration not approved: {last}")
        terminal_statuses = {"complete", "success", "error", "budget_blocked"}
        if completion_status in terminal_statuses and len(sample.strip()) >= min_assistant_chars:
            return {**last, "chatId": normalized_chat_id, "source": "api"}
        if last.get("ready") is True and len(sample.strip()) >= min_assistant_chars:
            return {**last, "chatId": normalized_chat_id, "source": "api"}
        time.sleep(2.0)
    raise AssertionError(f"DW stream did not complete within {timeout_sec}s via API for chat {normalized_chat_id}: {last}")
