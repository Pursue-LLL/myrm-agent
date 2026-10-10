"""Safe episodic forget business service.

[INPUT]
- SafeForgetRequestDTO, SafeForgetResponseDTO, ParentProbeResponseDTO from schemas.
- SafeEpisodicForgetEngine, SqliteEpisodicMemoryStore from harness safe_episodic_forget.

[OUTPUT]
- SafeForgetService providing authorization verification, competing parent probing, and safe episodic deletion.

[POS]
- Server-side domain service for Item 149 SafeEpisodicForgetSuite.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.memory.safe_episodic_forget import (
    ForgetRequest,
    InvalidationEvent,
    SafeEpisodicForgetEngine,
    SqliteEpisodicMemoryStore,
)

from app.schemas.safe_forget import (
    ParentProbeResponseDTO,
    SafeForgetRequestDTO,
    SafeForgetResponseDTO,
)

logger = logging.getLogger(__name__)


class SafeForgetService:
    """Service mediating safe episodic memory forgetting requests."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._store = SqliteEpisodicMemoryStore(db_path)
        self._engine = SafeEpisodicForgetEngine(self._store)
        self._audit_events: list[InvalidationEvent] = []
        self._engine.add_event_listener(self._record_audit_event)

    def _record_audit_event(self, event: InvalidationEvent) -> None:
        logger.info(
            "Emitted invalidation event for memory %s in tier %s",
            event.memory_id,
            event.tier,
        )
        self._audit_events.append(event)

    @property
    def store(self) -> SqliteEpisodicMemoryStore:
        """Access underlying store (primarily for tests and seeding)."""
        return self._store

    @property
    def audit_events(self) -> list[InvalidationEvent]:
        """List of audit events emitted after commit."""
        return list(self._audit_events)

    def probe_parents(
        self,
        memory_id: str,
        caller_session_id: str,
        allow_global: bool = True,
    ) -> ParentProbeResponseDTO:
        """Probe competing parent records across tiers before forgetting."""
        conn = self._store.get_connection()
        probe_res = self._engine.probe_parents(
            memory_id=memory_id,
            caller_session_id=caller_session_id,
            conn=conn,
            allow_global=allow_global,
        )
        return ParentProbeResponseDTO(
            memory_id=probe_res.memory_id,
            authorized=probe_res.authorized,
            episodic_exists=probe_res.episodic_exists,
            competing_tiers=[tier.value for tier in probe_res.competing_tiers],
            has_competing_parents=probe_res.has_competing_parents,
        )

    def forget_episodic(self, request: SafeForgetRequestDTO) -> SafeForgetResponseDTO:
        """Safely forget episodic memory enforcing session authorization and shared child retention."""
        req = ForgetRequest(
            memory_id=request.memory_id,
            caller_session_id=request.caller_session_id,
            user_id=request.user_id,
            allow_global=request.allow_global,
            reason=request.reason,
        )
        result = self._engine.forget_episodic(req)
        return SafeForgetResponseDTO(
            memory_id=result.memory_id,
            deleted=result.deleted,
            unauthorized=result.unauthorized,
            retained_shared_children=result.retained_shared_children,
            deleted_child_tables=list(result.deleted_child_tables),
            message=result.message,
        )


_instance: SafeForgetService | None = None


def get_safe_forget_service() -> SafeForgetService:
    """Return the singleton instance of SafeForgetService."""
    global _instance
    if _instance is None:
        _instance = SafeForgetService()
    return _instance


def reset_safe_forget_service() -> None:
    """Reset the singleton instance (used for testing)."""
    global _instance
    _instance = None
