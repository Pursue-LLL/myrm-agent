"""
[POS] app/services/memory/memory_unload_service.py
[INPUT] pathlib.Path, myrm_agent_harness.toolkits.memory.unload_guard, app/schemas/memory_unload.py
[OUTPUT] MemoryUnloadService, get_memory_unload_service

Business service mediating desktop and WebUI emergency flush and session finalize guard.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from threading import Lock

from myrm_agent_harness.toolkits.memory.unload_guard import (
    EmergencyFlushRequest,
    EmergencyFlushResult,
    EmergencySnapshotReason,
    UnfinalizedSessionSummary,
    UnloadGracefulFlushGuard,
)

from app.schemas.memory_unload import (
    AcknowledgeSessionRequestDTO,
    AcknowledgeSessionResponseDTO,
    EmergencyFlushRequestDTO,
    EmergencyFlushResponseDTO,
    ListUnfinalizedResponseDTO,
    UnfinalizedSessionDTO,
)

logger = logging.getLogger(__name__)


class MemoryUnloadService:
    """Service protecting sessions from data loss upon browser unload or desktop window close."""

    def __init__(self, guard: UnloadGracefulFlushGuard | None = None) -> None:
        if guard is not None:
            self._guard = guard
        else:
            base_dir_env = os.getenv("MYRM_UNLOAD_GUARD_DIR", ".myrm/unload_snapshots")
            storage_dir = Path(base_dir_env).resolve()
            self._guard = UnloadGracefulFlushGuard(storage_dir=storage_dir)
        logger.info("MemoryUnloadService initialized with storage_dir=%s", self._guard.storage_dir)

    def emergency_flush(self, request: EmergencyFlushRequestDTO) -> EmergencyFlushResponseDTO:
        """Execute crash-proof zero-LLM memory flush on page unload or window close."""
        reason_map: dict[str, EmergencySnapshotReason] = {
            "browser_unload": EmergencySnapshotReason.BROWSER_UNLOAD,
            "window_close_requested": EmergencySnapshotReason.WINDOW_CLOSE_REQUESTED,
            "session_switch": EmergencySnapshotReason.SESSION_SWITCH,
            "crash_prevention": EmergencySnapshotReason.CRASH_PREVENTION,
        }
        typed_reason = reason_map.get(request.reason, EmergencySnapshotReason.BROWSER_UNLOAD)

        harness_req = EmergencyFlushRequest(
            session_id=request.session_id,
            reason=typed_reason,
            active_goal=request.active_goal or "In-flight interactive user task",
            unsaved_notes=request.unsaved_notes,
            target_handoff_agent=request.target_handoff_agent,
        )

        result: EmergencyFlushResult = self._guard.flush(harness_req)

        return EmergencyFlushResponseDTO(
            success=True,
            handoff_id=result.handoff_id,
            snapshot_path=result.persisted_path,
            reason=typed_reason.value,
            finalized_at=time.time(),
        )

    def list_unfinalized(self) -> ListUnfinalizedResponseDTO:
        """Retrieve sessions that were terminated prematurely or await acknowledgment on startup."""
        unfinalized_list: list[UnfinalizedSessionSummary] = self._guard.list_unfinalized()
        dtos = [
            UnfinalizedSessionDTO(
                session_id=item.session_id,
                handoff_id=item.handoff_id,
                status="pending",
                created_at=item.created_at,
                active_goal=item.active_goal,
                snapshot_path=item.persisted_path,
            )
            for item in unfinalized_list
        ]
        return ListUnfinalizedResponseDTO(unfinalized_sessions=dtos)

    def acknowledge_session(self, request: AcknowledgeSessionRequestDTO) -> AcknowledgeSessionResponseDTO:
        """Acknowledge and mark an unfinalized session as claimed/dismissed."""
        pending_list = self._guard.list_unfinalized()
        target_handoff_id: str | None = None
        for item in pending_list:
            if item.session_id == request.session_id or item.handoff_id == request.session_id:
                target_handoff_id = item.handoff_id
                break

        if not target_handoff_id:
            return AcknowledgeSessionResponseDTO(
                success=False,
                session_id=request.session_id,
                message="Session not found or already claimed",
            )

        success = self._guard.acknowledge(handoff_id=target_handoff_id)
        msg = "Session acknowledged successfully" if success else "Session not found or already claimed"
        return AcknowledgeSessionResponseDTO(
            success=success,
            session_id=request.session_id,
            message=msg,
        )


_service_lock = Lock()
_service_instance: MemoryUnloadService | None = None


def get_memory_unload_service() -> MemoryUnloadService:
    """Return thread-safe singleton instance of MemoryUnloadService."""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            _service_instance = MemoryUnloadService()
        return _service_instance
