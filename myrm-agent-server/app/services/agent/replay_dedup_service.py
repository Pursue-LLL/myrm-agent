"""Service implementation for Multi-Agent Tool Replay History Deduplication & Harmonization (Item 57).

[INPUT]
- MergeReplayHistoryRequest, SyncSubagentStatusRequest, HeartbeatLeaseCheckRequest.

[OUTPUT]
- MergeReplayHistoryResponse, SyncSubagentStatusResponse, HeartbeatLeaseCheckResponse.

[POS]
- Server-side business service bridging Harness ToolReplayHistoryMerger and
  SubagentStatusHarmonizer to REST APIs.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.agent.sub_agents.replay_dedup import (
    SubagentStatusHarmonizer,
    ToolReplayHistoryMerger,
    ToolReplayItem,
    ToolReplayKindEnum,
    ToolReplayStatusEnum,
)

from app.schemas.replay_dedup import (
    HeartbeatLeaseCheckResponse,
    MergedReplayBatchDTO,
    MergeReplayHistoryRequest,
    MergeReplayHistoryResponse,
    SyncSubagentStatusRequest,
    SyncSubagentStatusResponse,
    ToolReplayItemDTO,
    ToolReplayKindDTOEnum,
    ToolReplayStatusDTOEnum,
)

logger: Final = logging.getLogger(__name__)


def _map_kind_dto_to_harness(kind: ToolReplayKindDTOEnum) -> ToolReplayKindEnum:
    match kind:
        case ToolReplayKindDTOEnum.READ_ONLY:
            return ToolReplayKindEnum.READ_ONLY
        case ToolReplayKindDTOEnum.MUTATING:
            return ToolReplayKindEnum.MUTATING
        case ToolReplayKindDTOEnum.SYSTEM:
            return ToolReplayKindEnum.SYSTEM


def _map_status_dto_to_harness(status: ToolReplayStatusDTOEnum) -> ToolReplayStatusEnum:
    match status:
        case ToolReplayStatusDTOEnum.IDLE:
            return ToolReplayStatusEnum.IDLE
        case ToolReplayStatusDTOEnum.RUNNING:
            return ToolReplayStatusEnum.RUNNING
        case ToolReplayStatusDTOEnum.PENDING_APPROVAL:
            return ToolReplayStatusEnum.PENDING_APPROVAL
        case ToolReplayStatusDTOEnum.COMPLETED:
            return ToolReplayStatusEnum.COMPLETED
        case ToolReplayStatusDTOEnum.FAILED:
            return ToolReplayStatusEnum.FAILED
        case ToolReplayStatusDTOEnum.CANCELLED:
            return ToolReplayStatusEnum.CANCELLED
        case ToolReplayStatusDTOEnum.TIMEOUT_TERMINATED:
            return ToolReplayStatusEnum.TIMEOUT_TERMINATED


def _map_status_harness_to_dto(status: ToolReplayStatusEnum) -> ToolReplayStatusDTOEnum:
    match status:
        case ToolReplayStatusEnum.IDLE:
            return ToolReplayStatusDTOEnum.IDLE
        case ToolReplayStatusEnum.RUNNING:
            return ToolReplayStatusDTOEnum.RUNNING
        case ToolReplayStatusEnum.PENDING_APPROVAL:
            return ToolReplayStatusDTOEnum.PENDING_APPROVAL
        case ToolReplayStatusEnum.COMPLETED:
            return ToolReplayStatusDTOEnum.COMPLETED
        case ToolReplayStatusEnum.FAILED:
            return ToolReplayStatusDTOEnum.FAILED
        case ToolReplayStatusEnum.CANCELLED:
            return ToolReplayStatusDTOEnum.CANCELLED
        case ToolReplayStatusEnum.TIMEOUT_TERMINATED:
            return ToolReplayStatusDTOEnum.TIMEOUT_TERMINATED


class ReplayDedupService:
    """Manages consecutive tool history deduplication and session-scoped subagent status harmonizers."""

    def __init__(self, default_lease_seconds: float = 30.0) -> None:
        self._default_lease_seconds = default_lease_seconds
        self._session_harmonizers: dict[str, SubagentStatusHarmonizer] = {}

    def _get_or_create_harmonizer(self, session_id: str) -> SubagentStatusHarmonizer:
        """Retrieves or creates a session-isolated SubagentStatusHarmonizer."""
        if session_id not in self._session_harmonizers:
            self._session_harmonizers[session_id] = SubagentStatusHarmonizer(
                lease_timeout_seconds=self._default_lease_seconds
            )
        return self._session_harmonizers[session_id]

    def merge_replay_history(self, req: MergeReplayHistoryRequest) -> MergeReplayHistoryResponse:
        """Compacts consecutive idempotent read-only tool sequences to conserve replay context."""
        merger = ToolReplayHistoryMerger(
            min_merge_count=req.min_merge_count,
            max_batch_size=req.max_batch_size,
        )

        harness_items: list[ToolReplayItem] = []
        for dto in req.items:
            harness_items.append(
                ToolReplayItem(
                    call_id=dto.call_id,
                    tool_name=dto.tool_name,
                    kind=_map_kind_dto_to_harness(dto.kind),
                    args=dto.args,
                    result_summary=dto.result_summary,
                    status=_map_status_dto_to_harness(dto.status),
                    start_time=dto.start_time,
                    end_time=dto.end_time,
                    estimated_tokens=dto.estimated_tokens,
                    subagent_id=dto.subagent_id,
                )
            )

        result = merger.merge_history(session_id=req.session_id, items=harness_items)

        batch_dtos: list[MergedReplayBatchDTO] = []
        for b in result.batches:
            batch_dtos.append(
                MergedReplayBatchDTO(
                    batch_id=b.batch_id,
                    tool_name=b.tool_name,
                    merged_count=b.merged_count,
                    item_ids=list(b.item_ids),
                    aggregated_args_summary=b.aggregated_args_summary,
                    aggregated_result_summary=b.aggregated_result_summary,
                    original_tokens=b.original_tokens,
                    compact_tokens=b.compact_tokens,
                    tokens_saved=b.tokens_saved,
                    start_time=b.start_time,
                    end_time=b.end_time,
                    final_status=_map_status_harness_to_dto(b.final_status),
                    subagent_id=b.subagent_id,
                )
            )

        unmerged_dtos: list[ToolReplayItemDTO] = []
        for u in result.unmerged_items:
            unmerged_dtos.append(
                ToolReplayItemDTO(
                    call_id=u.call_id,
                    tool_name=u.tool_name,
                    kind=ToolReplayKindDTOEnum(u.kind.value),
                    args=dict(u.args),
                    result_summary=u.result_summary,
                    status=_map_status_harness_to_dto(u.status),
                    start_time=u.start_time,
                    end_time=u.end_time,
                    estimated_tokens=u.estimated_tokens,
                    subagent_id=u.subagent_id,
                )
            )

        return MergeReplayHistoryResponse(
            session_id=result.session_id,
            original_items_count=result.original_items_count,
            deduplicated_items_count=result.deduplicated_items_count,
            total_original_tokens=result.total_original_tokens,
            total_compact_tokens=result.total_compact_tokens,
            tokens_saved=result.tokens_saved,
            reduction_ratio=result.reduction_ratio,
            batches=batch_dtos,
            unmerged_items=unmerged_dtos,
        )

    def sync_subagent_status(self, req: SyncSubagentStatusRequest) -> SyncSubagentStatusResponse:
        """Transitions subagent status adhering strictly to monotonic state machine rules."""
        harmonizer = self._get_or_create_harmonizer(req.session_id)
        current = harmonizer.get_status(req.subagent_id)

        # Auto-register if not yet enrolled
        if req.subagent_id not in harmonizer.get_all_statuses():
            harmonizer.register_subagent(req.subagent_id, initial_status=current)

        target_harness_status = _map_status_dto_to_harness(req.status)
        event = harmonizer.transition_status(
            subagent_id=req.subagent_id,
            new_status=target_harness_status,
            reason=req.reason,
        )

        return SyncSubagentStatusResponse(
            session_id=req.session_id,
            subagent_id=req.subagent_id,
            previous_status=_map_status_harness_to_dto(event.previous_status),
            new_status=_map_status_harness_to_dto(event.new_status),
            timestamp=event.timestamp,
            reason=event.reason,
            is_deadlock_prevented=event.is_deadlock_prevented,
        )

    def record_heartbeat(self, session_id: str, subagent_id: str) -> bool:
        """Refreshes the active lease for a running subagent."""
        if session_id not in self._session_harmonizers:
            return False
        return self._session_harmonizers[session_id].record_heartbeat(subagent_id)

    def check_watchdog_leases(self, session_id: str) -> HeartbeatLeaseCheckResponse:
        """Runs the deadlock prevention watchdog to terminate hung subagent leases."""
        harmonizer = self._get_or_create_harmonizer(session_id)
        events = harmonizer.check_watchdog()

        intervention_dtos: list[SyncSubagentStatusResponse] = []
        for ev in events:
            intervention_dtos.append(
                SyncSubagentStatusResponse(
                    session_id=session_id,
                    subagent_id=ev.subagent_id,
                    previous_status=_map_status_harness_to_dto(ev.previous_status),
                    new_status=_map_status_harness_to_dto(ev.new_status),
                    timestamp=ev.timestamp,
                    reason=ev.reason,
                    is_deadlock_prevented=ev.is_deadlock_prevented,
                )
            )

        status_snapshot: dict[str, ToolReplayStatusDTOEnum] = {
            sid: _map_status_harness_to_dto(st)
            for sid, st in harmonizer.get_all_statuses().items()
        }

        return HeartbeatLeaseCheckResponse(
            session_id=session_id,
            interventions_count=len(intervention_dtos),
            interventions=intervention_dtos,
            current_statuses=status_snapshot,
        )

    def get_subagent_statuses(self, session_id: str) -> Mapping[str, ToolReplayStatusDTOEnum]:
        """Returns the current state snapshot of all tracked subagents in a session."""
        if session_id not in self._session_harmonizers:
            return {}
        return {
            sid: _map_status_harness_to_dto(st)
            for sid, st in self._session_harmonizers[session_id].get_all_statuses().items()
        }

    def cleanup_chat(self, chat_id: str) -> None:
        """Releases session-scoped harmonizer state upon conversation teardown."""
        if chat_id in self._session_harmonizers:
            self._session_harmonizers[chat_id].clear()
            del self._session_harmonizers[chat_id]
            logger.info("Cleaned up replay harmonizer for chat: %s", chat_id)


_replay_dedup_service: ReplayDedupService | None = None


def get_replay_dedup_service() -> ReplayDedupService:
    """Singleton factory for ReplayDedupService."""
    global _replay_dedup_service
    if _replay_dedup_service is None:
        _replay_dedup_service = ReplayDedupService()
    return _replay_dedup_service
