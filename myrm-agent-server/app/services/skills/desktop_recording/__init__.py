"""Desktop workflow recording service — session registry and capture-loop lifecycle.

[POS]
Desktop recording service subpackage. Provides recording session management, AX capture task
and session state model.

[INPUT]
- app.services.skills.desktop_recording.capture_task
- app.services.skills.desktop_recording.session_manager
- app.services.skills.desktop_recording.state
"""

from app.services.skills.desktop_recording.capture_task import DesktopCaptureTask
from app.services.skills.desktop_recording.session_manager import (
    create_session,
    lookup_session,
    reset,
    session_count,
    stop_session,
)
from app.services.skills.desktop_recording.state import (
    SESSION_IDLE_TIMEOUT_SEC,
    RecordingSessionState,
)

__all__ = [
    "DesktopCaptureTask",
    "RecordingSessionState",
    "SESSION_IDLE_TIMEOUT_SEC",
    "create_session",
    "lookup_session",
    "reset",
    "session_count",
    "stop_session",
]
