"""Entitlement gap preflight — emit capability_gap SSE before Agent execution.

[INPUT]
- myrm_agent_harness.agent.meta_tools.discover_capability.capability_gap::detect_capability_gap (POS: entitlement gap detection SSOT)

[OUTPUT]
- build_entitlement_gap_sse_event: optional early SSE dict for disabled builtin tools
- CapabilityGapEmissionTracker: per-chat cooldown dedup for gap toasts
- reset_capability_gap_emission_tracker: test-only tracker reset

[POS]
Scans the user message against CAPABILITY_GAP_REGISTRY before the harness stream loop.
Does not modify Turn1 tool bindings or prompt cache — SSE-only hint for the WebUI toast.
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


def build_entitlement_gap_sse_event(
    *,
    message_id: str,
    user_text: str,
    active_tool_groups: frozenset[str],
    chat_id: str | None,
) -> dict[str, object] | None:
    """Build a capability_gap SSE payload when preflight detects a missing builtin tool."""
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
