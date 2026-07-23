"""Entitlement gap preflight — emit capability_gap SSE before Agent execution.

[INPUT]
- myrm_agent_harness.agent.meta_tools.discover_capability.capability_gap::detect_capability_gap (POS: entitlement gap detection SSOT)

[OUTPUT]
- build_entitlement_gap_sse_event: optional early SSE dict for disabled builtin tools
- build_web_search_config_gap_sse_event: SSE when web_search profile on but API missing/unreachable
- build_surface_unavailable_dedup_key: stable tracker key for IM/Web surface-unavailable toasts
- resolve_surface_unavailable_display_message: localized surface-unavailable copy (SSE + IM)
- resolve_web_search_config_gap_display_message: localized web_search config gap copy (IM fallback)
- CapabilityGapEmissionTracker: per-chat cooldown dedup for gap toasts
- reset_capability_gap_emission_tracker: test-only tracker reset

[POS]
Scans the user message against CAPABILITY_GAP_REGISTRY before the harness stream loop.
When render_ui is enabled in profile but the channel cannot mount inline UI, emits
surface_unavailable capability_gap (Web toast + IM ProgressUpdate). Does not modify
Turn1 tool bindings or prompt cache.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

from myrm_agent_harness.agent.meta_tools.discover_capability.capability_gap import (
    detect_capability_gap,
)

_MAX_TRACKED_CHATS = 4096
_GAP_TOAST_COOLDOWN_SECONDS = 900.0
_SURFACE_UNAVAILABLE_DEDUP_SUFFIX = "surface_unavailable"
_SEARCH_NOT_CONFIGURED_MESSAGES: dict[str, str] = {
    "en": "Web search is enabled but no search API is configured. Add a provider in Settings.",
    "zh": "已开启网页搜索，但未配置搜索 API。请前往设置添加搜索服务。",
}
_SEARCH_UNREACHABLE_MESSAGES: dict[str, str] = {
    "en": "Web search is enabled but the configured search provider is unreachable. Check Settings.",
    "zh": "已开启网页搜索，但配置的搜索服务不可用。请检查设置中的搜索服务。",
}
_SEARCH_SETTINGS_PATH = "/settings/search"
_SURFACE_UNAVAILABLE_MESSAGES: dict[str, str] = {
    "en": (
        "Inline interactive UI renders only in Web Chat and the desktop app. "
        "Telegram, scheduled tasks, and other channels cannot display inline forms or charts."
    ),
    "zh": "交互式 UI 仅在 Web 对话与桌面客户端内渲染；Telegram、定时任务等渠道无法显示内联表单或图表。",
}


def build_surface_unavailable_dedup_key(tool_id: str = "render_ui") -> str:
    """Return tracker key for surface-unavailable gap toasts."""
    return f"{tool_id}:{_SURFACE_UNAVAILABLE_DEDUP_SUFFIX}"


def resolve_surface_unavailable_display_message(locale: str | None) -> str:
    """Return localized surface-unavailable copy for SSE and channel progress."""
    if locale and locale.lower().startswith("zh"):
        return _SURFACE_UNAVAILABLE_MESSAGES["zh"]
    return _SURFACE_UNAVAILABLE_MESSAGES["en"]


class CapabilityGapEmissionTracker:
    """Tracks recent entitlement gap SSE per chat to limit repeated toasts."""

    def __init__(
        self,
        *,
        max_chats: int = _MAX_TRACKED_CHATS,
        cooldown_seconds: float = _GAP_TOAST_COOLDOWN_SECONDS,
    ) -> None:
        self._max_chats = max_chats
        self._cooldown_seconds = cooldown_seconds
        self._emitted: OrderedDict[str, dict[str, float]] = OrderedDict()
        self._lock = Lock()

    def should_emit(self, chat_id: str | None, tool_id: str) -> bool:
        if not chat_id:
            return True
        now = time.monotonic()
        with self._lock:
            chat_emissions = self._emitted.get(chat_id)
            if chat_emissions is None:
                return True
            last_emitted_at = chat_emissions.get(tool_id)
            if last_emitted_at is None:
                return True
            return (now - last_emitted_at) >= self._cooldown_seconds

    def mark_emitted(self, chat_id: str | None, tool_id: str) -> None:
        if not chat_id:
            return
        now = time.monotonic()
        with self._lock:
            if chat_id in self._emitted:
                self._emitted.move_to_end(chat_id)
            else:
                self._emitted[chat_id] = {}
            self._emitted[chat_id][tool_id] = now
            while len(self._emitted) > self._max_chats:
                self._emitted.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._emitted.clear()


_gap_emission_tracker = CapabilityGapEmissionTracker()


def reset_capability_gap_emission_tracker() -> None:
    """Test helper — clear in-memory chat dedup state."""
    _gap_emission_tracker.reset()


def _build_surface_unavailable_sse_event(
    *,
    message_id: str,
    user_text: str,
    active_tool_groups: frozenset[str],
    chat_id: str | None,
    channel_name: str,
    client_surface: str | None,
    locale: str | None,
) -> dict[str, object] | None:
    if "render_ui" not in active_tool_groups:
        return None
    from app.ai_agents.general_agent.tool_setup import _should_mount_render_ui_tools

    ui_intent = detect_capability_gap(
        user_text,
        active_tool_groups - frozenset({"render_ui"}),
    )
    if ui_intent is None or ui_intent.tool_id != "render_ui":
        return None
    if _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name=channel_name,
        client_surface=client_surface,
    ):
        return None
    dedup_key = build_surface_unavailable_dedup_key(ui_intent.tool_id)
    if not _gap_emission_tracker.should_emit(chat_id, dedup_key):
        return None
    _gap_emission_tracker.mark_emitted(chat_id, dedup_key)
    return {
        "type": "capability_gap",
        "messageId": message_id,
        "data": {
            "tool_id": ui_intent.tool_id,
            "tool_group": ui_intent.tool_group,
            "reason": _SURFACE_UNAVAILABLE_DEDUP_SUFFIX,
            "display_message": resolve_surface_unavailable_display_message(locale),
        },
    }


def _resolve_web_search_config_message(*, reason: str, locale: str | None) -> str:
    is_zh = bool(locale and locale.lower().startswith("zh"))
    if reason == "unreachable":
        return _SEARCH_UNREACHABLE_MESSAGES["zh" if is_zh else "en"]
    return _SEARCH_NOT_CONFIGURED_MESSAGES["zh" if is_zh else "en"]


def resolve_web_search_config_gap_display_message(*, reason: str, locale: str | None) -> str:
    """Return localized web_search config gap copy for SSE and channel progress."""
    return _resolve_web_search_config_message(reason=reason, locale=locale)


def build_web_search_config_gap_sse_event(
    *,
    message_id: str,
    web_search_profile_enabled: bool,
    enable_web_search: bool,
    search_is_user_configured: bool,
    chat_id: str | None,
    locale: str | None,
) -> dict[str, object] | None:
    """Emit capability_gap when profile enables web_search but runtime search is unavailable."""
    if not web_search_profile_enabled or enable_web_search:
        return None
    reason = "not_configured" if not search_is_user_configured else "unreachable"
    dedup_key = f"web_search:{reason}"
    if not _gap_emission_tracker.should_emit(chat_id, dedup_key):
        return None
    _gap_emission_tracker.mark_emitted(chat_id, dedup_key)
    return {
        "type": "capability_gap",
        "messageId": message_id,
        "data": {
            "tool_id": "web_search",
            "tool_group": "web",
            "reason": reason,
            "display_message": _resolve_web_search_config_message(reason=reason, locale=locale),
            "settings_path": _SEARCH_SETTINGS_PATH,
        },
    }


def build_entitlement_gap_sse_event(
    *,
    message_id: str,
    user_text: str,
    active_tool_groups: frozenset[str],
    chat_id: str | None,
    channel_name: str = "web_chat",
    client_surface: str | None = None,
    locale: str | None = None,
) -> dict[str, object] | None:
    """Build a capability_gap SSE payload when preflight detects a missing builtin tool."""
    surface_event = _build_surface_unavailable_sse_event(
        message_id=message_id,
        user_text=user_text,
        active_tool_groups=active_tool_groups,
        chat_id=chat_id,
        channel_name=channel_name,
        client_surface=client_surface,
        locale=locale,
    )
    if surface_event is not None:
        return surface_event

    hit = detect_capability_gap(user_text, active_tool_groups)
    if hit is None:
        return None
    if not _gap_emission_tracker.should_emit(chat_id, hit.tool_id):
        return None
    _gap_emission_tracker.mark_emitted(chat_id, hit.tool_id)
    return {
        "type": "capability_gap",
        "messageId": message_id,
        "data": {"tool_id": hit.tool_id, "tool_group": hit.tool_group},
    }
