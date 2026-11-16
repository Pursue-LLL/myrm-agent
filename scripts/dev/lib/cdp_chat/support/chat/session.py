"""Chat session calls over the REST API.

[INPUT]
- cdp_chat.support.api_client::_E2E_API_REQUEST_ATTEMPTS, _e2e_api_post_json, _e2e_api_urlopen, get_e2e_api_url, resolve_e2e_api_base (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.timeouts::signoff_parallel_force_chat_timeout_sec (POS: Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers)

[OUTPUT]
- create_e2e_chat_via_api, cancel_e2e_chat_agent_via_api: create a chat, cancel its in-flight agent stream
- chat_id_from_path: the chat id of a page path
- fetch_chat_messages: the stored messages of a chat
- steer_chat_message: steer an in-flight turn

[POS]
Chat session calls of the E2E over the REST API: create, cancel, read messages, steer.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from cdp_chat.support.api_client import (
    _E2E_API_REQUEST_ATTEMPTS,
    _e2e_api_post_json,
    _e2e_api_urlopen,
    get_e2e_api_url,
    resolve_e2e_api_base,
)
from cdp_chat.support.timeouts import signoff_parallel_force_chat_timeout_sec


def create_e2e_chat_via_api(chat_id: str, *, api_url: str | None = None) -> None:
    """Create a chat session on the active E2E API base (signoff clarify API leg)."""
    resolved = resolve_e2e_api_base(api_url or get_e2e_api_url())
    if not resolved:
        raise RuntimeError("E2E_API_BASE missing for create_e2e_chat_via_api")
    url = f"{resolved.rstrip('/')}/api/v1/chats/"
    timeout_sec = signoff_parallel_force_chat_timeout_sec(15.0)
    _e2e_api_post_json(url, {"chat_id": chat_id}, timeout_sec=timeout_sec)


def cancel_e2e_chat_agent_via_api(chat_id: str, *, api_url: str | None = None) -> bool:
    """Cancel in-flight agent-stream on chat_id (releases AgentBusy session for retry)."""
    resolved = resolve_e2e_api_base(api_url or get_e2e_api_url())
    if not resolved:
        return False
    url = f"{resolved.rstrip('/')}/api/v1/agents/chats/{chat_id}/cancel"
    try:
        result = _e2e_api_post_json(url, {}, timeout_sec=10.0, max_attempts=1)
    except (TimeoutError, OSError, urllib.error.URLError, urllib.error.HTTPError):
        return False
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict) and data.get("cancelled") is True:
            return True
    return False


_CHAT_ID_PATH_RE = re.compile(
    r"^/(?:chat/)?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|c-[a-z0-9\-]+)$",
    re.IGNORECASE,
)


def chat_id_from_path(path: str) -> str | None:
    match = _CHAT_ID_PATH_RE.match(path.strip())
    return match.group(1) if match else None


def fetch_chat_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> list[dict[str, object]]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    req = urllib.request.Request(
        f"{resolved_api}/api/v1/chats/{chat_id}/messages",
        headers={"Accept": "application/json"},
    )
    try:
        with _e2e_api_urlopen(
            req, timeout_sec=timeout_sec, max_attempts=max_attempts
        ) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    messages = data.get("messages")
    return messages if isinstance(messages, list) else []


def steer_chat_message(
    chat_id: str,
    message: str,
    *,
    api_url: str | None = None,
) -> dict[str, object]:
    """Steer an in-flight agent turn via REST (no Chrome UI surface required)."""
    normalized_chat = chat_id.strip()
    normalized_message = message.strip()
    if not normalized_chat or not normalized_message:
        return {"ok": False, "err": "missing-chat-id-or-message"}
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    payload = _e2e_api_post_json(
        f"{resolved_api}/api/v1/agents/chats/{normalized_chat}/steer",
        {"message": normalized_message},
        timeout_sec=30.0,
    )
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and data.get("steered") is True:
            return {"ok": True, "mode": "steerApi", "chatId": normalized_chat}
        if payload.get("success") is True:
            return {"ok": True, "mode": "steerApi", "chatId": normalized_chat}
    return {"ok": False, "err": "steer-api-rejected", "payload": payload}
