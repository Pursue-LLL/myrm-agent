"""Service layer for Visual Kanban Multi-Agent Workflow Dispatcher and Card Handoff (Item 66).

[INPUT]
- CreateCardRequest, TransitionCardRequest, UpdateProgressRequest, FlagBlockerRequest schemas.
- KanbanWorkflowDispatcher from harness.

[OUTPUT]
- KanbanCardDTO, HandoffEventDTO, KanbanWorkspaceStateDTO.

[POS]
- Bridge between FastAPI kanban dispatcher router and underlying harness KanbanWorkflowDispatcher.
"""

from __future__ import annotations

import threading
from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.kanban_dispatcher import (
    HandoffEvent,
    KanbanCard,
    KanbanColumn,
    KanbanWorkflowDispatcher,
    KanbanWorkspaceState,
)

from app.schemas.kanban_dispatcher import (
    CardHandoffStatusDTOEnum,
    CreateCardRequest,
    FlagBlockerRequest,
    HandoffEventDTO,
    KanbanCardDTO,
    KanbanColumnDTOEnum,
    KanbanWorkspaceStateDTO,
    TransitionCardRequest,
    UpdateProgressRequest,
)


class KanbanDispatcherService:
    """Thread-safe orchestration service managing multi-agent kanban workspaces and card handoffs."""

    _dispatcher: ClassVar[KanbanWorkflowDispatcher] = KanbanWorkflowDispatcher()
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _to_card_dto(cls, c: KanbanCard) -> KanbanCardDTO:
        return KanbanCardDTO(
            card_id=c.card_id,
            title=c.title,
            description=c.description,
            column=KanbanColumnDTOEnum(c.column.value),
            assigned_agent_id=c.assigned_agent_id,
            progress_percent=c.progress_percent,
            handoff_status=CardHandoffStatusDTOEnum(c.handoff_status.value),
            handoff_payload=dict(c.handoff_payload),
            blocker_reason=c.blocker_reason,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )

    @classmethod
    def _to_event_dto(cls, e: HandoffEvent) -> HandoffEventDTO:
        return HandoffEventDTO(
            event_id=e.event_id,
            card_id=e.card_id,
            from_agent_id=e.from_agent_id,
            to_agent_id=e.to_agent_id,
            from_column=KanbanColumnDTOEnum(e.from_column.value),
            to_column=KanbanColumnDTOEnum(e.to_column.value),
            context_summary=e.context_summary,
            timestamp=e.timestamp,
        )

    @classmethod
    def _to_state_dto(cls, s: KanbanWorkspaceState) -> KanbanWorkspaceStateDTO:
        return KanbanWorkspaceStateDTO(
            workspace_id=s.workspace_id,
            title=s.title,
            cards=[cls._to_card_dto(c) for c in s.cards],
            handoff_history=[cls._to_event_dto(e) for e in s.handoff_history],
            active_blockers=s.active_blockers,
        )

    @classmethod
    def create_card(cls, req: CreateCardRequest) -> KanbanCardDTO:
        """Create a new work item card in the kanban workspace."""
        with cls._lock:
            col = KanbanColumn(req.column.value)
            card = cls._dispatcher.create_card(
                workspace_id=req.workspace_id,
                title=req.title,
                description=req.description,
                column=col,
                assigned_agent_id=req.assigned_agent_id,
            )
            return cls._to_card_dto(card)

    @classmethod
    def get_card(cls, workspace_id: str, card_id: str) -> KanbanCardDTO | None:
        """Fetch card details by workspace ID and card ID."""
        with cls._lock:
            card = cls._dispatcher.get_card(workspace_id, card_id)
            if card is None:
                return None
            return cls._to_card_dto(card)

    @classmethod
    def list_cards(
        cls,
        workspace_id: str,
        column: KanbanColumnDTOEnum | None = None,
    ) -> list[KanbanCardDTO]:
        """List cards in workspace, optionally filtered by column."""
        with cls._lock:
            col_filter = KanbanColumn(column.value) if column else None
            cards = cls._dispatcher.list_cards(workspace_id, col_filter)
            return [cls._to_card_dto(c) for c in cards]

    @classmethod
    def transition_card(
        cls,
        workspace_id: str,
        card_id: str,
        req: TransitionCardRequest,
    ) -> KanbanCardDTO:
        """Move card to a target column and trigger cross-agent packaging."""
        with cls._lock:
            target_col = KanbanColumn(req.target_column.value)
            card = cls._dispatcher.transition_card(
                workspace_id=workspace_id,
                card_id=card_id,
                target_column=target_col,
                handoff_context=req.handoff_context,
                target_agent_id=req.target_agent_id,
            )
            return cls._to_card_dto(card)

    @classmethod
    def update_progress(
        cls,
        workspace_id: str,
        card_id: str,
        req: UpdateProgressRequest,
    ) -> KanbanCardDTO:
        """Update real-time execution progress percentage."""
        with cls._lock:
            card = cls._dispatcher.update_progress(
                workspace_id=workspace_id,
                card_id=card_id,
                progress_percent=req.progress_percent,
            )
            return cls._to_card_dto(card)

    @classmethod
    def flag_blocker(
        cls,
        workspace_id: str,
        card_id: str,
        req: FlagBlockerRequest,
    ) -> KanbanCardDTO:
        """Flag a card as blocked."""
        with cls._lock:
            card = cls._dispatcher.flag_blocker(
                workspace_id=workspace_id,
                card_id=card_id,
                reason=req.reason,
            )
            return cls._to_card_dto(card)

    @classmethod
    def resolve_blocker(cls, workspace_id: str, card_id: str) -> KanbanCardDTO:
        """Resolve an active blocker on a card."""
        with cls._lock:
            card = cls._dispatcher.resolve_blocker(workspace_id, card_id)
            return cls._to_card_dto(card)

    @classmethod
    def get_workspace_state(cls, workspace_id: str) -> KanbanWorkspaceStateDTO:
        """Retrieve complete state snapshot of a kanban workspace."""
        with cls._lock:
            state = cls._dispatcher.get_workspace_state(workspace_id)
            return cls._to_state_dto(state)

    @classmethod
    def clear(cls) -> None:
        """Reset service state for isolated test runs."""
        with cls._lock:
            cls._dispatcher.clear()
