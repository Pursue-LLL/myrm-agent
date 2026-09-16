"""Entitlement gap preflight — emit capability_gap SSE before Agent execution.

[INPUT]
- (none — self-contained; reads no harness capability-gap registry)

[OUTPUT]
- build_web_search_config_gap_sse_event: SSE when web_search profile on but API missing/unreachable
- resolve_web_search_config_gap_display_message: localized web_search config gap copy (IM fallback)
- CapabilityGapEmissionTracker: per-chat cooldown dedup for gap toasts
- get_capability_gap_emission_tracker: shared process-wide dedup tracker accessor
- reset_capability_gap_emission_tracker: test-only tracker reset

[POS]
Emits capability_gap SSE for web_search configuration gaps before the harness stream loop.
Does not modify Turn1 tool bindings or prompt cache.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

_MAX_TRACKED_CHATS = 4096
_GAP_TOAST_COOLDOWN_SECONDS = 900.0
_SEARCH_NOT_CONFIGURED_MESSAGES: dict[str, str] = {
    "en": "Web search is enabled but no search API is configured. Add a provider in Settings.",
    "zh": "已开启网页搜索，但未配置搜索 API。请前往设置添加搜索服务。",
}
_SEARCH_UNREACHABLE_MESSAGES: dict[str, str] = {
    "en": "Web search is enabled but the configured search provider is unreachable. Check Settings.",
    "zh": "已开启网页搜索，但配置的搜索服务不可用。请检查设置中的搜索服务。",
}
_SEARCH_SETTINGS_PATH = "/settings/search"


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


def get_capability_gap_emission_tracker() -> CapabilityGapEmissionTracker:
    """Return the process-wide capability gap dedup tracker."""
    return _gap_emission_tracker


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
