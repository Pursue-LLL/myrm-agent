"""Service mediating Pi Harness v2 Multi-Lane Parallel Execution Model (Item 50).

[INPUT]
- CreateLaneRequest, AppendNodeRequest, DispatchOperationRequest,
  CompleteOperationRequest, CancelOperationRequest.

[OUTPUT]
- MultiLaneService coordinating session-scoped parallel lanes and shared append-only trees.

[POS]
- Server-side service layer for multi-lane execution model.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.sub_agents.multi_lane import (
    LaneInfo,
    LaneOperation,
    MultiLaneSessionCoordinator,
    MultiLaneSessionSnapshot,
    TreeNode,
)

from app.schemas.multi_lane import (
    LaneInfoDTO,
    LaneOperationDTO,
    LaneStateEnum,
    MultiLaneSnapshotDTO,
    OpStatusEnum,
    PrimitiveValue,
    TreeNodeDTO,
)

logger = logging.getLogger(__name__)


def _node_to_dto(node: TreeNode) -> TreeNodeDTO:
    return TreeNodeDTO(
        node_id=node.node_id,
        parent_id=node.parent_id,
        lane_id=node.lane_id,
        node_type=node.node_type,
        content=node.content,
        created_at=node.created_at,
        metadata=dict(node.metadata),
    )


def _lane_to_dto(lane: LaneInfo) -> LaneInfoDTO:
    return LaneInfoDTO(
        lane_id=lane.lane_id,
        display_name=lane.display_name,
        state=LaneStateEnum(lane.state),
        current_leaf_id=lane.current_leaf_id,
        active_op_id=lane.active_op_id,
        total_ops=lane.total_ops,
        created_at=lane.created_at,
    )


def _op_to_dto(op: LaneOperation) -> LaneOperationDTO:
    return LaneOperationDTO(
        op_id=op.op_id,
        lane_id=op.lane_id,
        name=op.name,
        payload=dict(op.payload),
        status=OpStatusEnum(op.status),
        created_at=op.created_at,
        started_at=op.started_at,
        completed_at=op.completed_at,
        error_message=op.error_message,
        result_node_id=op.result_node_id,
    )


def _snapshot_to_dto(snapshot: MultiLaneSessionSnapshot) -> MultiLaneSnapshotDTO:
    return MultiLaneSnapshotDTO(
        session_id=snapshot.session_id,
        lanes={k: _lane_to_dto(v) for k, v in snapshot.lanes.items()},
        total_nodes=snapshot.total_nodes,
        active_lanes_count=snapshot.active_lanes_count,
        recent_op_logs=[_op_to_dto(op) for op in snapshot.recent_op_logs],
    )


class MultiLaneService:
    """Session coordinator cache and bridge for multi-lane execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._coordinators: dict[str, MultiLaneSessionCoordinator] = {}

    def get_or_create_coordinator(self, session_id: str) -> MultiLaneSessionCoordinator:
        """Get or initialize a MultiLaneSessionCoordinator for the given session."""
        with self._lock:
            if session_id not in self._coordinators:
                self._coordinators[session_id] = MultiLaneSessionCoordinator(
                    session_id=session_id
                )
            return self._coordinators[session_id]

    async def create_lane(
        self,
        session_id: str,
        lane_id: str,
        display_name: str,
        fork_from_node_id: str | None = None,
    ) -> LaneInfoDTO:
        coordinator = self.get_or_create_coordinator(session_id)
        lane = await coordinator.create_lane(
            lane_id=lane_id,
            display_name=display_name,
            fork_from_node_id=fork_from_node_id,
        )
        return _lane_to_dto(lane)

    async def append_node(
        self,
        session_id: str,
        lane_id: str,
        content: str,
        node_type: str = "message",
        metadata: dict[str, PrimitiveValue] | None = None,
    ) -> TreeNodeDTO:
        coordinator = self.get_or_create_coordinator(session_id)
        node = await coordinator.append_node(
            lane_id=lane_id,
            content=content,
            node_type=node_type,
            metadata=metadata or {},
        )
        return _node_to_dto(node)

    async def dispatch_operation(
        self,
        session_id: str,
        lane_id: str,
        name: str,
        payload: dict[str, PrimitiveValue] | None = None,
    ) -> LaneOperationDTO:
        coordinator = self.get_or_create_coordinator(session_id)
        op = await coordinator.dispatch_operation(
            lane_id=lane_id,
            name=name,
            payload=payload or {},
        )
        return _op_to_dto(op)

    async def complete_operation(
        self,
        session_id: str,
        lane_id: str,
        op_id: str,
        result_content: str | None = None,
        error: str | None = None,
    ) -> LaneOperationDTO:
        coordinator = self.get_or_create_coordinator(session_id)
        op = await coordinator.complete_operation(
            lane_id=lane_id,
            op_id=op_id,
            result_content=result_content,
            error=error,
        )
        return _op_to_dto(op)

    async def cancel_operation(
        self,
        session_id: str,
        lane_id: str,
        op_id: str,
        reason: str | None = None,
    ) -> LaneOperationDTO:
        coordinator = self.get_or_create_coordinator(session_id)
        op = await coordinator.cancel_operation(
            lane_id=lane_id,
            op_id=op_id,
            reason=reason,
        )
        return _op_to_dto(op)

    async def get_op_log(
        self,
        session_id: str,
        lane_id: str,
    ) -> list[LaneOperationDTO]:
        coordinator = self.get_or_create_coordinator(session_id)
        ops = await coordinator.get_op_log(lane_id)
        return [_op_to_dto(op) for op in ops]

    async def get_snapshot(
        self,
        session_id: str,
        recent_ops_limit: int = 50,
    ) -> MultiLaneSnapshotDTO:
        coordinator = self.get_or_create_coordinator(session_id)
        snapshot = await coordinator.get_snapshot(recent_ops_limit=recent_ops_limit)
        return _snapshot_to_dto(snapshot)

    def reset_session(self, session_id: str) -> None:
        """Clear cache for the given session ID."""
        with self._lock:
            self._coordinators.pop(session_id, None)


_multi_lane_service_instance: MultiLaneService | None = None


def get_multi_lane_service() -> MultiLaneService:
    """Return singleton instance of MultiLaneService."""
    global _multi_lane_service_instance
    if _multi_lane_service_instance is None:
        _multi_lane_service_instance = MultiLaneService()
    return _multi_lane_service_instance
