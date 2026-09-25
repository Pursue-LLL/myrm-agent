"""Desktop recording session state model.

[INPUT]
- myrm_agent_harness.api::DesktopRecordedEvent, SynthesizedSkillDraft

[OUTPUT]
- RecordingSessionState, SESSION_IDLE_TIMEOUT_SEC, _MAX_EVENTS_PER_SESSION

[POS]
Skill recording runtime state container.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.api import DesktopRecordedEvent, SynthesizedSkillDraft

_MAX_EVENTS_PER_SESSION = 500

SESSION_IDLE_TIMEOUT_SEC = 600


class RecordingSessionState:
    def __init__(self, session_id: str, app_scope: str = "all") -> None:
        self.session_id: str = session_id
        self.app_scope: str = app_scope
        self.status: str = "recording"
        self.started_at: float = time.time()
        self.stopped_at: float | None = None
        self.events: list[DesktopRecordedEvent] = []
        self.latest_draft: SynthesizedSkillDraft | None = None
        # Capture-loop state: whether platform AX capture is driving this session, and why not
        # when it is unavailable (unsupported platform, missing permission, capture failure).
        self.capture_active: bool = False
        self.capture_error: str | None = None
        self.last_seen_at: float = time.time()

    def touch(self) -> None:
        """Record client activity so an abandoned session can be reaped."""
        self.last_seen_at = time.time()

    def add_event(self, event: DesktopRecordedEvent) -> None:
        if len(self.events) >= _MAX_EVENTS_PER_SESSION:
            self.events.pop(0)
        self.events.append(event)
