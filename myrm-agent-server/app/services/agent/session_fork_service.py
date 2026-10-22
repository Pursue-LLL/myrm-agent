"""Service mediating Pi Harness v2 Deterministic Subagent Session Fork Primitive (Item 51).

[INPUT]
- ForkChildSessionRequest, DeriveChildIdRequest.

[OUTPUT]
- SessionForkService coordinating deterministic child derivation, safe replay reattach,
  and branch/tree node duplication.

[POS]
- Server-side service layer for deterministic session fork subsystem.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.sub_agents.session_fork import (
    ChildSessionLink,
    DeterministicSessionForkManager,
    ForkedSessionNode,
    ForkResult,
    ForkScope,
)

from app.schemas.session_fork import (
    ChildSessionLinkDTO,
    ChildSessionListResponse,
    DeriveChildIdResponse,
    ForkChildSessionRequest,
    ForkedSessionNodeDTO,
    ForkResultDTO,
    ForkScopeEnum,
)

logger = logging.getLogger(__name__)


def _node_dto_to_domain(dto: ForkedSessionNodeDTO) -> ForkedSessionNode:
    return ForkedSessionNode(
        node_id=dto.node_id,
        parent_id=dto.parent_id,
        node_type=dto.node_type,
        content=dto.content,
        created_at=dto.created_at,
        metadata=dict(dto.metadata),
    )


def _node_domain_to_dto(node: ForkedSessionNode) -> ForkedSessionNodeDTO:
    return ForkedSessionNodeDTO(
        node_id=node.node_id,
        parent_id=node.parent_id,
        node_type=node.node_type,
        content=node.content,
        created_at=node.created_at,
        metadata=dict(node.metadata),
    )


def _link_domain_to_dto(link: ChildSessionLink) -> ChildSessionLinkDTO:
    return ChildSessionLinkDTO(
        child_session_id=link.child_session_id,
        parent_session_id=link.parent_session_id,
        tool_call_id=link.tool_call_id,
        fork_scope=ForkScopeEnum(link.fork_scope),
        created_at=link.created_at,
        reattach_count=link.reattach_count,
        last_attached_at=link.last_attached_at,
    )


def _result_domain_to_dto(res: ForkResult) -> ForkResultDTO:
    return ForkResultDTO(
        child_session_id=res.child_session_id,
        parent_session_id=res.parent_session_id,
        tool_call_id=res.tool_call_id,
        is_reattached=res.is_reattached,
        fork_scope=ForkScopeEnum(res.fork_scope),
        copied_nodes_count=res.copied_nodes_count,
        root_node_id=res.root_node_id,
        leaf_node_id=res.leaf_node_id,
    )


class SessionForkService:
    """Singleton service wrapping DeterministicSessionForkManager."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._manager: DeterministicSessionForkManager = (
            DeterministicSessionForkManager()
        )

    def derive_child_session_id(
        self, parent_session_id: str, tool_call_id: str
    ) -> DeriveChildIdResponse:
        derived_id = self._manager.derive_child_session_id(
            parent_session_id=parent_session_id,
            tool_call_id=tool_call_id,
        )
        return DeriveChildIdResponse(
            child_session_id=derived_id,
            parent_session_id=parent_session_id,
            tool_call_id=tool_call_id,
        )

    def fork_child_session(self, request: ForkChildSessionRequest) -> ForkResultDTO:
        domain_scope = (
            ForkScope.TREE
            if request.scope == ForkScopeEnum.TREE
            else ForkScope.BRANCH
        )
        domain_nodes = [
            _node_dto_to_domain(node) for node in request.parent_nodes
        ]

        result = self._manager.fork_child_session(
            parent_session_id=request.parent_session_id,
            tool_call_id=request.tool_call_id,
            scope=domain_scope,
            parent_nodes=domain_nodes,
            target_leaf_id=request.target_leaf_id,
        )
        return _result_domain_to_dto(result)

    def get_child_session(self, child_session_id: str) -> ChildSessionLinkDTO | None:
        link = self._manager.get_child_session(child_session_id)
        if link is None:
            return None
        return _link_domain_to_dto(link)

    def get_child_nodes(self, child_session_id: str) -> list[ForkedSessionNodeDTO]:
        nodes = self._manager.get_child_nodes(child_session_id)
        return [_node_domain_to_dto(node) for node in nodes]

    def list_children_for_parent(
        self, parent_session_id: str
    ) -> ChildSessionListResponse:
        children = self._manager.list_children_for_parent(parent_session_id)
        dtos = [_link_domain_to_dto(c) for c in children]
        return ChildSessionListResponse(
            parent_session_id=parent_session_id,
            children=dtos,
            total_children=len(dtos),
        )

    def reset(self) -> None:
        self._manager.reset()


_session_fork_service_instance: SessionForkService | None = None


def get_session_fork_service() -> SessionForkService:
    """Return singleton instance of SessionForkService."""
    global _session_fork_service_instance
    if _session_fork_service_instance is None:
        _session_fork_service_instance = SessionForkService()
    return _session_fork_service_instance
