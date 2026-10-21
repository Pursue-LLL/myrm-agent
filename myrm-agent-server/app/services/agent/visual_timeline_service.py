"""Service implementation for Multi-Agent Visual Timeline & Cherry-Pick Rollback (Item 61).

[INPUT]
- TimelineNodeRecordRequest, TimelineFilterCriteriaRequest.
- Harness visual_timeline::{
    TimelineJournal, CherryPickRollbackEngine, TimelineNode, RollbackResult,
    ActorType, OperationType, RollbackStatus, TimelineFilterCriteria,
  }

[OUTPUT]
- TimelineNodeDTO, RollbackResultDTO, list[TimelineNodeDTO].

[POS]
- Server-side business service managing visual multi-agent chronological journal
  and surgical non-destructive cherry-pick rollbacks.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from myrm_agent_harness.agent.sub_agents.visual_timeline import (
    ActorType,
    CherryPickRollbackEngine,
    OperationType,
    RollbackResult,
    RollbackStatus,
    TimelineFilterCriteria,
    TimelineJournal,
    TimelineNode,
)

from app.schemas.visual_timeline import (
    ActorTypeDTOEnum,
    OperationTypeDTOEnum,
    RollbackResultDTO,
    RollbackStatusDTOEnum,
    TimelineFilterCriteriaRequest,
    TimelineNodeDTO,
    TimelineNodeRecordRequest,
)

logger: Final = logging.getLogger(__name__)


def _map_actor_type_dto_to_harness(dto: ActorTypeDTOEnum) -> ActorType:
    match dto:
        case ActorTypeDTOEnum.HUMAN_USER:
            return ActorType.HUMAN_USER
        case ActorTypeDTOEnum.LOCAL_AGENT:
            return ActorType.LOCAL_AGENT
        case ActorTypeDTOEnum.CLOUD_AGENT:
            return ActorType.CLOUD_AGENT
        case ActorTypeDTOEnum.SYSTEM_ORCHESTRATOR:
            return ActorType.SYSTEM_ORCHESTRATOR


def _map_actor_type_harness_to_dto(actor: ActorType) -> ActorTypeDTOEnum:
    match actor:
        case ActorType.HUMAN_USER:
            return ActorTypeDTOEnum.HUMAN_USER
        case ActorType.LOCAL_AGENT:
            return ActorTypeDTOEnum.LOCAL_AGENT
        case ActorType.CLOUD_AGENT:
            return ActorTypeDTOEnum.CLOUD_AGENT
        case ActorType.SYSTEM_ORCHESTRATOR:
            return ActorTypeDTOEnum.SYSTEM_ORCHESTRATOR


def _map_operation_dto_to_harness(dto: OperationTypeDTOEnum) -> OperationType:
    match dto:
        case OperationTypeDTOEnum.FILE_MODIFY:
            return OperationType.FILE_MODIFY
        case OperationTypeDTOEnum.FILE_CREATE:
            return OperationType.FILE_CREATE
        case OperationTypeDTOEnum.FILE_DELETE:
            return OperationType.FILE_DELETE
        case OperationTypeDTOEnum.TOOL_EXECUTION:
            return OperationType.TOOL_EXECUTION
        case OperationTypeDTOEnum.GIT_COMMIT:
            return OperationType.GIT_COMMIT


def _map_operation_harness_to_dto(op: OperationType) -> OperationTypeDTOEnum:
    match op:
        case OperationType.FILE_MODIFY:
            return OperationTypeDTOEnum.FILE_MODIFY
        case OperationType.FILE_CREATE:
            return OperationTypeDTOEnum.FILE_CREATE
        case OperationType.FILE_DELETE:
            return OperationTypeDTOEnum.FILE_DELETE
        case OperationType.TOOL_EXECUTION:
            return OperationTypeDTOEnum.TOOL_EXECUTION
        case OperationType.GIT_COMMIT:
            return OperationTypeDTOEnum.GIT_COMMIT


def _map_rollback_status_harness_to_dto(status: RollbackStatus) -> RollbackStatusDTOEnum:
    match status:
        case RollbackStatus.SUCCESS:
            return RollbackStatusDTOEnum.SUCCESS
        case RollbackStatus.CONFLICT_DETECTED:
            return RollbackStatusDTOEnum.CONFLICT_DETECTED
        case RollbackStatus.ALREADY_ROLLED_BACK:
            return RollbackStatusDTOEnum.ALREADY_ROLLED_BACK
        case RollbackStatus.NODE_NOT_FOUND:
            return RollbackStatusDTOEnum.NODE_NOT_FOUND


def _map_node_to_dto(node: TimelineNode) -> TimelineNodeDTO:
    return TimelineNodeDTO(
        node_id=node.node_id,
        session_id=node.session_id,
        actor_id=node.actor_id,
        actor_name=node.actor_name,
        actor_type=_map_actor_type_harness_to_dto(node.actor_type),
        operation_type=_map_operation_harness_to_dto(node.operation_type),
        file_path=node.file_path,
        line_start=node.line_start,
        line_end=node.line_end,
        before_content=node.before_content,
        after_content=node.after_content,
        diff_summary=node.diff_summary,
        parent_node_id=node.parent_node_id,
        is_rolled_back=node.is_rolled_back,
        timestamp=node.timestamp,
        metadata=dict(node.metadata),
    )


def _map_rollback_result_to_dto(result: RollbackResult) -> RollbackResultDTO:
    return RollbackResultDTO(
        node_id=result.node_id,
        status=_map_rollback_status_harness_to_dto(result.status),
        file_path=result.file_path,
        restored_content=result.restored_content,
        conflict_reason=result.conflict_reason,
        rollback_timestamp=result.rollback_timestamp,
    )


class VisualTimelineService:
    """Business service governing multi-agent timeline tracking and cherry-pick rollback."""

    def __init__(
        self,
        journal: TimelineJournal | None = None,
        engine: CherryPickRollbackEngine | None = None,
    ) -> None:
        self._journal = journal if journal is not None else TimelineJournal()
        self._engine = (
            engine if engine is not None else CherryPickRollbackEngine(journal=self._journal)
        )

    @property
    def journal(self) -> TimelineJournal:
        return self._journal

    @property
    def engine(self) -> CherryPickRollbackEngine:
        return self._engine

    def clear(self) -> None:
        """Clear all stored timeline nodes and in-memory VFS files."""
        self._journal.clear()
        self._engine._vfs_store.clear()

    def record_node(self, request: TimelineNodeRecordRequest) -> TimelineNodeDTO:
        """Record an atomic timeline node and index it."""
        node_id = f"node-{uuid.uuid4().hex[:10]}"
        node = TimelineNode(
            node_id=node_id,
            session_id=request.session_id,
            actor_id=request.actor_id,
            actor_name=request.actor_name,
            actor_type=_map_actor_type_dto_to_harness(request.actor_type),
            operation_type=_map_operation_dto_to_harness(request.operation_type),
            file_path=request.file_path,
            line_start=request.line_start,
            line_end=request.line_end,
            before_content=request.before_content,
            after_content=request.after_content,
            diff_summary=request.diff_summary,
            parent_node_id=request.parent_node_id,
            metadata=dict(request.metadata),
        )
        self._journal.record_node(node)
        logger.info(
            "Recorded timeline node %s by %s (%s)",
            node.node_id,
            node.actor_name,
            node.operation_type.value,
        )
        return _map_node_to_dto(node)

    def get_node(self, node_id: str) -> TimelineNodeDTO | None:
        """Fetch a single timeline node by its unique ID."""
        node = self._journal.get_node(node_id)
        if node is None:
            return None
        return _map_node_to_dto(node)

    def query_nodes(self, request: TimelineFilterCriteriaRequest) -> list[TimelineNodeDTO]:
        """Query chronological timeline nodes filtered by multi-dimensional criteria."""
        criteria = TimelineFilterCriteria(
            actor_id=request.actor_id,
            actor_type=_map_actor_type_dto_to_harness(request.actor_type)
            if request.actor_type
            else None,
            file_path=request.file_path,
            operation_type=_map_operation_dto_to_harness(request.operation_type)
            if request.operation_type
            else None,
            start_time=request.start_time,
            end_time=request.end_time,
        )
        nodes = self._journal.query_nodes(
            session_id=request.session_id,
            criteria=criteria,
        )
        return [_map_node_to_dto(n) for n in nodes]

    def rollback_node(self, target_node_id: str) -> RollbackResultDTO:
        """Execute a surgical cherry-pick rollback against the targeted node."""
        result = self._engine.rollback_node(target_node_id)
        logger.info(
            "Rollback node %s executed with status: %s",
            target_node_id,
            result.status.value,
        )
        return _map_rollback_result_to_dto(result)

    def set_file_content(self, file_path: str, content: str) -> None:
        """Convenience method for tests and VFS mocking."""
        self._engine.set_file_content(file_path, content)

    def get_file_content(self, file_path: str) -> str:
        """Convenience method to retrieve current VFS content."""
        return self._engine.get_file_content(file_path)


_GLOBAL_VISUAL_TIMELINE_SERVICE: VisualTimelineService | None = None


def get_visual_timeline_service() -> VisualTimelineService:
    """Return the global singleton instance of VisualTimelineService."""
    global _GLOBAL_VISUAL_TIMELINE_SERVICE
    if _GLOBAL_VISUAL_TIMELINE_SERVICE is None:
        _GLOBAL_VISUAL_TIMELINE_SERVICE = VisualTimelineService()
    return _GLOBAL_VISUAL_TIMELINE_SERVICE
