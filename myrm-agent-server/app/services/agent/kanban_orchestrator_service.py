"""Service layer for Visual Multi-Agent Kanban Orchestrator and Card Lifecycle Dispatcher."""

from __future__ import annotations

import uuid
from typing import List, Optional

from myrm_agent_harness.agent.sub_agents.kanban_orchestrator import (
    CardArtifactDTO as HarnessCardArtifactDTO,
)
from myrm_agent_harness.agent.sub_agents.kanban_orchestrator import (
    CardPriorityEnum as HarnessCardPriorityEnum,
)
from myrm_agent_harness.agent.sub_agents.kanban_orchestrator import (
    KanbanBoardStateDTO as HarnessBoardStateDTO,
)
from myrm_agent_harness.agent.sub_agents.kanban_orchestrator import (
    KanbanCardDTO as HarnessCardDTO,
)
from myrm_agent_harness.agent.sub_agents.kanban_orchestrator import (
    KanbanCardLifecycleDispatcher,
)
from myrm_agent_harness.agent.sub_agents.kanban_orchestrator import (
    KanbanLaneEnum as HarnessLaneEnum,
)

from app.schemas.kanban_orchestrator import (
    CardArtifactDTO,
    CardPriorityEnum,
    CreateBoardRequestDTO,
    CreateCardRequestDTO,
    DecomposeGoalRequestDTO,
    DecomposeGoalResponseDTO,
    HumanOverrideRequestDTO,
    KanbanBoardStateDTO,
    KanbanCardDTO,
    KanbanLaneEnum,
    MountArtifactRequestDTO,
    TransitionCardRequestDTO,
    TransitionCardResponseDTO,
)


class KanbanOrchestratorService:
    """Singleton service managing multi-agent Kanban boards, dependency DAGs, and card lifecycles."""

    _instance: Optional[KanbanOrchestratorService] = None

    def __init__(self) -> None:
        self.dispatcher = KanbanCardLifecycleDispatcher()

    @classmethod
    def get_instance(cls) -> KanbanOrchestratorService:
        """Retrieve or initialize singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance for test isolation."""
        cls._instance = None

    def _convert_artifact(self, art: HarnessCardArtifactDTO) -> CardArtifactDTO:
        return CardArtifactDTO(
            artifact_id=art.artifact_id,
            name=art.name,
            artifact_type=art.artifact_type,
            file_path=art.file_path,
            content_preview=art.content_preview,
            mounted_at=art.mounted_at,
        )

    def _convert_card(self, card: HarnessCardDTO) -> KanbanCardDTO:
        return KanbanCardDTO(
            card_id=card.card_id,
            board_id=card.board_id,
            title=card.title,
            description=card.description,
            lane=KanbanLaneEnum(card.lane.value),
            priority=CardPriorityEnum(card.priority.value),
            assigned_agent=card.assigned_agent,
            depends_on=list(card.depends_on),
            blocked_by=list(card.blocked_by),
            sandbox_subdir=card.sandbox_subdir,
            artifacts=[self._convert_artifact(a) for a in card.artifacts],
            created_at=card.created_at,
            updated_at=card.updated_at,
            completed_at=card.completed_at,
        )

    def _convert_board(self, board: HarnessBoardStateDTO) -> KanbanBoardStateDTO:
        return KanbanBoardStateDTO(
            board_id=board.board_id,
            session_id=board.session_id,
            title=board.title,
            cards={c_id: self._convert_card(c) for c_id, c in board.cards.items()},
            created_at=board.created_at,
            updated_at=board.updated_at,
        )

    def create_board(self, req: CreateBoardRequestDTO) -> KanbanBoardStateDTO:
        """Initialize a new persistent Kanban board for a session."""
        board_id = f"board-{uuid.uuid4().hex[:8]}"
        board = self.dispatcher.create_board(
            board_id=board_id,
            session_id=req.session_id,
            title=req.title,
        )
        return self._convert_board(board)

    def get_board(self, board_id: str) -> KanbanBoardStateDTO:
        """Retrieve board state by ID."""
        board = self.dispatcher.get_board(board_id)
        return self._convert_board(board)

    def list_boards(self) -> List[KanbanBoardStateDTO]:
        """List all active boards."""
        return [self._convert_board(b) for b in self.dispatcher.list_boards()]

    def create_card(self, board_id: str, req: CreateCardRequestDTO) -> KanbanCardDTO:
        """Create a new task card with dependency validation and card-scoped sandbox assignment."""
        harness_prio = HarnessCardPriorityEnum(req.priority.value)
        harness_lane = HarnessLaneEnum(req.initial_lane.value) if req.initial_lane else None

        card = self.dispatcher.create_card(
            board_id=board_id,
            title=req.title,
            description=req.description,
            assigned_agent=req.assigned_agent,
            depends_on=req.depends_on,
            priority=harness_prio,
            initial_lane=harness_lane,
        )
        return self._convert_card(card)

    def transition_card(
        self,
        board_id: str,
        card_id: str,
        req: TransitionCardRequestDTO,
    ) -> TransitionCardResponseDTO:
        """Transition card across swimlanes with auto-unblock cascade upon completion."""
        target_lane = HarnessLaneEnum(req.target_lane.value)
        card, unlocked = self.dispatcher.transition_card(
            board_id=board_id,
            card_id=card_id,
            target_lane=target_lane,
            actor=req.actor,
        )
        return TransitionCardResponseDTO(
            card=self._convert_card(card),
            unlocked_cards=unlocked,
        )

    def mount_artifact(
        self,
        board_id: str,
        card_id: str,
        req: MountArtifactRequestDTO,
    ) -> CardArtifactDTO:
        """Mount execution output artifact to card."""
        art = self.dispatcher.mount_artifact(
            board_id=board_id,
            card_id=card_id,
            name=req.name,
            artifact_type=req.artifact_type,
            file_path=req.file_path,
            content_preview=req.content_preview,
        )
        return self._convert_artifact(art)

    def human_override(
        self,
        board_id: str,
        card_id: str,
        req: HumanOverrideRequestDTO,
    ) -> TransitionCardResponseDTO:
        """Human-in-the-loop override for agent reassignment, priority shift, or drag-and-drop."""
        prio = HarnessCardPriorityEnum(req.new_priority.value) if req.new_priority else None
        lane = HarnessLaneEnum(req.new_lane.value) if req.new_lane else None

        card, unlocked = self.dispatcher.human_override(
            board_id=board_id,
            card_id=card_id,
            new_agent=req.new_agent,
            new_priority=prio,
            new_lane=lane,
        )
        return TransitionCardResponseDTO(
            card=self._convert_card(card),
            unlocked_cards=unlocked,
        )

    def decompose_goal(
        self,
        board_id: str,
        req: DecomposeGoalRequestDTO,
    ) -> DecomposeGoalResponseDTO:
        """Boss Agent (Orchestrator) automated decomposition into sequenced DAG task cards."""
        cards = self.dispatcher.auto_decompose_goal(
            board_id=board_id,
            goal=req.goal,
            specialist_roster=req.specialist_roster,
        )
        return DecomposeGoalResponseDTO(
            board_id=board_id,
            created_cards=[self._convert_card(c) for c in cards],
        )


def get_kanban_orchestrator_service() -> KanbanOrchestratorService:
    """FastAPI dependency provider for KanbanOrchestratorService."""
    return KanbanOrchestratorService.get_instance()
