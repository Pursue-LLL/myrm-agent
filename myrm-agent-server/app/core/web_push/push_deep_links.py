"""Resolve Web Push click-through URLs from ServerEventBus events.

Mirrors in-app SSE navigation targets in the WebUI (see useGlobalEvents router.push).
Returns same-origin relative paths only; the service worker validates before openWindow.

[INPUT]
- app.services.event.app_event_bus::AppEvent, AppEventType

[OUTPUT]
- resolve_push_url: Map AppEvent → relative path for push payload `url`

[POS]
Pure routing helper for WebPushDispatcher. Reuses chat path convention from
app.remote_access.mobile_deep_link::build_web_chat_url (path-only, no base URL).
"""

from __future__ import annotations

from urllib.parse import quote

from app.services.event.app_event_bus import AppEvent, AppEventType

_DEFAULT_URL = "/"
_SETTINGS_SYSTEM = "/settings/system"
_SETTINGS_CHANNELS = "/settings/channels"
_SETTINGS_INTEGRATIONS = "/settings/integrationCatalog"


def _chat_path(chat_id: str) -> str | None:
    normalized = chat_id.strip()
    if not normalized:
        return None
    return f"/{quote(normalized, safe='')}"


def _first_chat_id(data: dict[str, object]) -> str:
    for key in ("chat_id", "session_id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    meta = data.get("meta_data")
    if isinstance(meta, dict):
        meta_chat = meta.get("chat_id")
        if isinstance(meta_chat, str) and meta_chat.strip():
            return meta_chat.strip()

    return ""


def _approval_id(data: dict[str, object]) -> str:
    value = data.get("approval_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def resolve_push_url(event: AppEvent) -> str:
    """Return a same-origin relative path for notification click-through."""
    data: dict[str, object] = dict(event.data)
    event_type = event.event_type

    if event_type == AppEventType.APPROVAL_REQUIRED:
        chat_id = _first_chat_id(data)
        approval_id = _approval_id(data)
        if chat_id:
            path = _chat_path(chat_id)
            if path and approval_id:
                return f"{path}?approval={quote(approval_id, safe='')}"
            if path:
                return path
        return _DEFAULT_URL

    if event_type in {
        AppEventType.GOAL_TERMINAL,
        AppEventType.BACKGROUND_TASK_DONE,
        AppEventType.SYSTEM_NOTIFICATION,
    }:
        chat_id = _first_chat_id(data)
        if chat_id:
            path = _chat_path(chat_id)
            if path:
                return path
        return _DEFAULT_URL

    if event_type in {AppEventType.HEALTH_ALERT, AppEventType.BUDGET_ALERT}:
        return _SETTINGS_SYSTEM

    if event_type == AppEventType.CHANNEL_DISCONNECTED:
        return _SETTINGS_CHANNELS

    if event_type == AppEventType.OAUTH_REAUTH_REQUIRED:
        return _SETTINGS_INTEGRATIONS

    return _DEFAULT_URL
