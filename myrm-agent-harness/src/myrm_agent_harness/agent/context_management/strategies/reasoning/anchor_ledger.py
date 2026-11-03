"""Reasoning Anchor Ledger.

Maintains immutable, session-scoped reasoning anchors. Provides bounded
retention, cross-subagent scope routing, and prompt cache-friendly text rendering.

[INPUT]
- .anchor_extractor::ReasoningAnchor (POS: Anchor data model)

[OUTPUT]
- SessionAnchorLedger: Session-scoped anchor ledger
- get_session_anchor_ledger: Registry lookup for active session ledger

[POS]
Pure in-memory ledger with bounded capacity to guarantee zero CPU/memory thrashing.
The rendered block is frozen per user turn (render_for_turn) so injecting it never
changes the prompt prefix between tool rounds.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

from .anchor_extractor import ReasoningAnchor

_LEDGERS_LOCK = threading.Lock()
_SESSION_LEDGERS: dict[str, SessionAnchorLedger] = {}
_DEFAULT_MAX_ANCHORS = 10
_MAX_ACTIVE_SESSIONS = 500


class SessionAnchorLedger:
    """Bounded, thread-safe ledger for reasoning anchors within a session."""

    def __init__(self, session_id: str, *, max_anchors: int = _DEFAULT_MAX_ANCHORS) -> None:
        self.session_id = session_id
        self.max_anchors = max_anchors
        self._anchors: list[ReasoningAnchor] = []
        self._turn_snapshot: tuple[str, str] | None = None
        self._lock = threading.Lock()

    def record_anchor(self, anchor: ReasoningAnchor) -> None:
        """Record a single anchor, deduplicating by content and respecting max capacity."""
        with self._lock:
            # Deduplicate by content text
            for existing in self._anchors:
                if existing.content == anchor.content:
                    return
            self._anchors.append(anchor)
            if len(self._anchors) > self.max_anchors:
                # FIFO drop oldest anchors
                self._anchors = self._anchors[-self.max_anchors :]

    def record_anchors(self, anchors: Sequence[ReasoningAnchor]) -> None:
        """Batch record anchors."""
        for anc in anchors:
            self.record_anchor(anc)

    def get_anchors(self, *, category: str | None = None) -> list[ReasoningAnchor]:
        """Return a copy of active anchors, optionally filtered by category."""
        with self._lock:
            if category is None:
                return list(self._anchors)
            return [a for a in self._anchors if a.category == category]

    def clear(self) -> None:
        """Clear all anchors in this ledger."""
        with self._lock:
            self._anchors.clear()
            self._turn_snapshot = None

    def render_anchors_context(self, *, max_count: int | None = None) -> str:
        """Render active anchors into a clean, compact system injection block."""
        with self._lock:
            return self._render_locked(max_count)

    def render_for_turn(self, turn_key: str) -> str:
        """Render the block frozen when ``turn_key`` was first seen.

        Anchors recorded while the turn is still running show up from the next
        turn on, so the user message that carries the block keeps identical bytes
        across every tool round of the turn and the provider prompt cache keeps
        matching the whole prefix behind it.
        """
        with self._lock:
            if self._turn_snapshot is None or self._turn_snapshot[0] != turn_key:
                self._turn_snapshot = (turn_key, self._render_locked(None))
            return self._turn_snapshot[1]

    def _render_locked(self, max_count: int | None) -> str:
        if not self._anchors:
            return ""
        selected = self._anchors if max_count is None else self._anchors[-max_count:]
        lines = [f"- {a.to_compact_string()}" for a in selected]
        return "[PRESERVED REASONING ANCHORS & CONSTRAINTS]\n" + "\n".join(lines)


def get_session_anchor_ledger(session_id: str, *, max_anchors: int = _DEFAULT_MAX_ANCHORS) -> SessionAnchorLedger:
    """Get or create the singleton anchor ledger for a specific session."""
    with _LEDGERS_LOCK:
        if session_id not in _SESSION_LEDGERS:
            if len(_SESSION_LEDGERS) >= _MAX_ACTIVE_SESSIONS:
                # Evict oldest registered session ledger to prevent unbounded memory growth
                oldest_key = next(iter(_SESSION_LEDGERS))
                del _SESSION_LEDGERS[oldest_key]
            _SESSION_LEDGERS[session_id] = SessionAnchorLedger(session_id, max_anchors=max_anchors)
        return _SESSION_LEDGERS[session_id]


def clear_session_anchor_ledger(session_id: str) -> None:
    """Remove and cleanup the session anchor ledger."""
    with _LEDGERS_LOCK:
        _SESSION_LEDGERS.pop(session_id, None)
