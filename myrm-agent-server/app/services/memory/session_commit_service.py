# [POS]: app/services/memory/session_commit_service.py
# [INPUT]: app.schemas.session_commit, myrm_agent_harness.toolkits.memory
# [OUTPUT]: SessionCommitService, get_session_commit_service

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    CommitBoundaryKind,
    CommitTaskStatus,
    MemoryDiffAudit,
    MemoryDiffChangeKind,
    MemoryDiffItem,
    SessionArchiveMessage,
    SessionCommitResult,
    SessionCommitTwoPhaseEngine,
)

from app.schemas.session_commit import (
    CommitTaskStatusResponseDTO,
    MemoryDiffAuditResponseDTO,
    MemoryDiffItemDTO,
    MemoryDiffStatsDTO,
    SessionCommitRequest,
    SessionCommitResponseDTO,
)

logger = logging.getLogger(__name__)


def _to_boundary_kind(raw: str) -> CommitBoundaryKind:
    try:
        return CommitBoundaryKind(raw.lower())
    except ValueError:
        return CommitBoundaryKind.MANUAL


def _to_task_dto(task: CommitTaskStatus) -> CommitTaskStatusResponseDTO:
    stats_dto = None
    if task.diff_stats is not None:
        stats_dto = MemoryDiffStatsDTO(
            total_added=task.diff_stats.total_added,
            total_updated=task.diff_stats.total_updated,
            total_superseded=task.diff_stats.total_superseded,
            total_deleted=task.diff_stats.total_deleted,
        )
    return CommitTaskStatusResponseDTO(
        task_id=task.task_id,
        session_id=task.session_id,
        archive_id=task.archive_id,
        phase=task.phase.value,
        boundary_kind=task.boundary_kind.value,
        created_at=task.created_at,
        completed_at=task.completed_at,
        error=task.error,
        message_count=task.message_count,
        diff_stats=stats_dto,
    )


def _to_audit_dto(audit: MemoryDiffAudit) -> MemoryDiffAuditResponseDTO:
    items = [
        MemoryDiffItemDTO(
            change_kind=c.change_kind.value,
            memory_type=c.memory_type,
            item_id=c.item_id,
            before_summary=c.before_summary,
            after_summary=c.after_summary,
            timestamp=c.timestamp,
        )
        for c in audit.changes
    ]
    stats = MemoryDiffStatsDTO(
        total_added=audit.stats.total_added,
        total_updated=audit.stats.total_updated,
        total_superseded=audit.stats.total_superseded,
        total_deleted=audit.stats.total_deleted,
    )
    return MemoryDiffAuditResponseDTO(
        session_id=audit.session_id,
        archive_id=audit.archive_id,
        task_id=audit.task_id,
        timestamp=audit.timestamp,
        boundary_kind=audit.boundary_kind.value,
        changes=items,
        stats=stats,
    )


class SessionCommitService:
    """Service orchestrating two-phase session commit and memory_diff auditing."""

    def __init__(self, engine: SessionCommitTwoPhaseEngine | None = None) -> None:
        self._engine = engine or SessionCommitTwoPhaseEngine(base_storage_dir=Path(".sessions"))

    def commit_session(self, req: SessionCommitRequest) -> SessionCommitResponseDTO:
        """Phase 1: Persist messages synchronously and schedule Phase 2 if gated."""
        domain_messages = [
            SessionArchiveMessage(
                role=m.role,
                content=m.content,
                tool_calls=tuple(m.tool_calls),
                tool_results=tuple(m.tool_results),
                timestamp=m.timestamp,
                referenced_uris=tuple(m.referenced_uris),
            )
            for m in req.messages
        ]
        boundary = _to_boundary_kind(req.boundary_kind)

        result: SessionCommitResult = self._engine.commit(
            session_id=req.session_id,
            messages=domain_messages,
            boundary_kind=boundary,
            metadata=req.metadata,
        )

        return SessionCommitResponseDTO(
            task_id=result.task_id,
            session_id=result.session_id,
            archive_id=result.archive_id,
            phase1_persisted=result.phase1_persisted,
            messages_path=result.messages_path,
            phase2_scheduled=result.phase2_scheduled,
        )

    def execute_phase2(
        self,
        task_id: str,
        simulated_diffs: list[MemoryDiffItemDTO] | None = None,
    ) -> CommitTaskStatusResponseDTO:
        """Phase 2: Generate abstract/overview, write memory_diff.json, and stamp .done."""
        domain_diffs: list[MemoryDiffItem] = []
        if simulated_diffs:
            for d in simulated_diffs:
                domain_diffs.append(
                    MemoryDiffItem(
                        change_kind=MemoryDiffChangeKind(d.change_kind),
                        memory_type=d.memory_type,
                        item_id=d.item_id,
                        before_summary=d.before_summary,
                        after_summary=d.after_summary,
                        timestamp=d.timestamp,
                    )
                )

        completed_task = self._engine.execute_phase2_sync(
            task_id=task_id,
            memory_diff_items=domain_diffs,
        )
        return _to_task_dto(completed_task)

    def get_task(self, task_id: str) -> CommitTaskStatusResponseDTO | None:
        """Fetch status of commit task."""
        task = self._engine.get_task(task_id)
        return _to_task_dto(task) if task else None

    def get_memory_diff(self, session_id: str, archive_id: str) -> MemoryDiffAuditResponseDTO | None:
        """Read memory_diff.json from archive bundle."""
        audit = self._engine.get_memory_diff(session_id, archive_id)
        return _to_audit_dto(audit) if audit else None

    def list_archives(self, session_id: str) -> list[str]:
        """List sequential archive IDs for session."""
        return self._engine.list_session_archives(session_id)


@lru_cache
def get_session_commit_service() -> SessionCommitService:
    """Singleton provider for SessionCommitService."""
    return SessionCommitService()
