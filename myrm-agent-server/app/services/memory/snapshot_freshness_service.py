"""Service layer coordinating memory snapshot digests, dirty state tracking, and delta patches.

[INPUT]
- Session initialization requests, write delta records, and inspection queries.

[OUTPUT]
- MemorySnapshotDigestDTO, DirectDiskReadHintDTO, DeltaPatchBlockDTO, and SnapshotFreshnessStateDTO.

[POS]
- Server-side business service for Item 157 SnapshotLagAwareMemoryFreshnessAndDiskVerificationContractSuite.
"""

from __future__ import annotations

from app.schemas.snapshot_freshness import (
    DeltaPatchBlockDTO,
    DirectDiskReadHintDTO,
    InitSnapshotRequest,
    MemorySnapshotDigestDTO,
    RecordWriteRequest,
    SessionWriteDeltaDTO,
    SnapshotFreshnessStateDTO,
)
from myrm_agent_harness.agent.middlewares.memory_context.snapshot_freshness import (
    DeltaPatchBlock,
    DirectDiskReadHint,
    MemorySnapshotDigest,
    SnapshotFreshnessState,
    SnapshotFreshnessTracker,
)


class SnapshotFreshnessService:
    """Business service orchestrating snapshot generation digests, dirty flags, and delta patches."""

    def __init__(self, tracker: SnapshotFreshnessTracker | None = None) -> None:
        self.tracker = tracker or SnapshotFreshnessTracker()

    @staticmethod
    def _state_to_dto(state: SnapshotFreshnessState) -> SnapshotFreshnessStateDTO:
        return SnapshotFreshnessStateDTO(
            session_id=state.session_id,
            snapshot_digest=state.snapshot_digest,
            is_dirty=state.is_dirty,
            deltas=[
                SessionWriteDeltaDTO(
                    key=d.key,
                    content=d.content,
                    turn_index=d.turn_index,
                    written_at=d.written_at,
                    action=d.action,
                )
                for d in state.deltas
            ],
            latest_disk_version=state.latest_disk_version,
        )

    def init_session_snapshot(
        self, req: InitSnapshotRequest
    ) -> MemorySnapshotDigestDTO:
        """Initialize and seal the memory snapshot generation digest for a session."""
        digest: MemorySnapshotDigest = self.tracker.init_session_snapshot(
            session_id=req.session_id,
            initial_content=req.initial_content,
            items_count=req.items_count,
        )
        return MemorySnapshotDigestDTO(
            digest=digest.digest,
            session_id=digest.session_id,
            created_at=digest.created_at,
            initial_items_count=digest.initial_items_count,
        )

    def record_write(
        self, req: RecordWriteRequest
    ) -> SnapshotFreshnessStateDTO:
        """Record an ongoing memory write event to disk and mark snapshot as dirty."""
        state = self.tracker.record_write(
            session_id=req.session_id,
            key=req.key,
            content=req.content,
            turn_index=req.turn_index,
            action=req.action,
        )
        return self._state_to_dto(state)

    def get_state(self, session_id: str) -> SnapshotFreshnessStateDTO:
        """Fetch current staleness and dirty state of a session."""
        state = self.tracker.get_state(session_id)
        return self._state_to_dto(state)

    def generate_disk_read_hint(self, session_id: str) -> DirectDiskReadHintDTO:
        """Generate a direct-disk verification contract hint."""
        hint: DirectDiskReadHint = self.tracker.generate_disk_read_hint(session_id)
        return DirectDiskReadHintDTO(
            session_id=hint.session_id,
            hint_message=hint.hint_message,
            affected_keys=hint.affected_keys,
            is_dirty=hint.is_dirty,
        )

    def render_delta_patch(self, session_id: str) -> DeltaPatchBlockDTO:
        """Render intra-session memory delta patch block for append-only prompt injection."""
        block: DeltaPatchBlock = self.tracker.render_delta_patch(session_id)
        return DeltaPatchBlockDTO(
            header=block.header,
            patches=block.patches,
            formatted_block=block.formatted_block,
        )

    def reset_session(self, session_id: str) -> None:
        """Reset and wipe tracking state for a finished session."""
        self.tracker.reset_session(session_id)
