"""[INPUT] schemas/debate_workroom.py, myrm_agent_harness.agent.sub_agents.debate.
[OUTPUT] DebateWorkroomService: Service layer managing multi-agent debate workrooms and kanban task bindings.
[POS] Core service coordinating workroom lifecycle, task decomposition, turn arguments, and kanban sync.
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.agent.sub_agents.debate import (
    DebateKanbanBridge,
    DebateParticipant,
    DebatePhase,
    DebateRoomState,
    DebateSubtask,
    DebateTurn,
    MultiAgentDebateManager,
)

from app.schemas.debate_workroom import (
    CreateDebateRoomRequest,
    DebateParticipantDTO,
    DebateRoomListResponse,
    DebateRoomResponse,
    DebateSubtaskDTO,
    DebateTurnDTO,
    PostArgumentRequest,
)


class DebateWorkroomService:
    """Service providing multi-agent debate coordination and Kanban integration."""

    _instance: DebateWorkroomService | None = None

    def __init__(self, manager: MultiAgentDebateManager | None = None) -> None:
        self._manager = manager or MultiAgentDebateManager()

    @classmethod
    def get_instance(cls) -> DebateWorkroomService:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _turn_to_dto(turn: DebateTurn) -> DebateTurnDTO:
        return DebateTurnDTO(
            turn_id=turn.turn_id,
            speaker_id=turn.speaker_id,
            speaker_name=turn.speaker_name,
            role=turn.role,
            phase=turn.phase,
            round_index=turn.round_index,
            thesis=turn.thesis,
            counter_points=turn.counter_points,
            evidence=turn.evidence,
            confidence=turn.confidence,
            kanban_task_id=turn.kanban_task_id,
            created_at=turn.created_at,
        )

    @staticmethod
    def _subtask_to_dto(subtask: DebateSubtask) -> DebateSubtaskDTO:
        return DebateSubtaskDTO(
            task_id=subtask.task_id,
            title=subtask.title,
            description=subtask.description,
            assigned_agent_id=subtask.assigned_agent_id,
            assigned_role=subtask.assigned_role,
            status=subtask.status,
            kanban_task_id=subtask.kanban_task_id,
        )

    def _to_response(self, state: DebateRoomState) -> DebateRoomResponse:
        return DebateRoomResponse(
            room_id=state.room_id,
            chat_id=state.chat_id,
            topic=state.topic,
            leader_agent_id=state.leader_agent_id,
            phase=state.phase,
            round_index=state.round_index,
            max_rounds=state.max_rounds,
            participants=[
                DebateParticipantDTO(
                    agent_id=p.agent_id,
                    name=p.name,
                    role=p.role,
                    model=p.model,
                )
                for p in state.participants
            ],
            subtasks=[self._subtask_to_dto(s) for s in state.subtasks],
            turns=[self._turn_to_dto(t) for t in state.turns],
            consensus_decision=state.consensus_decision,
            kanban_board_id=state.kanban_board_id,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )

    def create_room(
        self,
        chat_id: str,
        request: CreateDebateRoomRequest,
    ) -> DebateRoomResponse:
        """Create a new debate workroom."""
        room_id = request.room_id or f"room-{uuid.uuid4().hex[:8]}"
        participants = [
            DebateParticipant(
                agent_id=p.agent_id,
                name=p.name,
                role=p.role,
                model=p.model,
            )
            for p in request.participants
        ]

        state = self._manager.create_room(
            room_id=room_id,
            chat_id=chat_id,
            topic=request.topic,
            leader_agent_id=request.leader_agent_id,
            participants=participants,
            max_rounds=request.max_rounds,
            kanban_board_id=request.kanban_board_id,
        )
        return self._to_response(state)

    def get_room(self, room_id: str) -> DebateRoomResponse | None:
        """Fetch debate room state."""
        state = self._manager.get_room(room_id)
        if not state:
            return None
        return self._to_response(state)

    def list_rooms(self, chat_id: str) -> DebateRoomListResponse:
        """List all debate rooms for a given chat."""
        rooms = self._manager.list_rooms(chat_id=chat_id)
        return DebateRoomListResponse(
            chat_id=chat_id,
            rooms=[self._to_response(r) for r in rooms],
            total=len(rooms),
        )

    def decompose(
        self,
        room_id: str,
        subtasks_dto: list[DebateSubtaskDTO],
    ) -> DebateRoomResponse:
        """Leader decomposes the root topic into subtasks."""
        subtasks = [
            DebateSubtask(
                task_id=s.task_id,
                title=s.title,
                description=s.description,
                assigned_agent_id=s.assigned_agent_id,
                assigned_role=s.assigned_role,
                status=s.status,
                kanban_task_id=s.kanban_task_id,
            )
            for s in subtasks_dto
        ]
        state = self._manager.decompose_task(room_id=room_id, subtasks=subtasks)
        return self._to_response(state)

    def post_argument(
        self,
        room_id: str,
        request: PostArgumentRequest,
    ) -> DebateTurnDTO:
        """Post an argument or cross-examination in the debate stream."""
        turn = self._manager.post_argument(
            room_id=room_id,
            speaker_id=request.speaker_id,
            thesis=request.thesis,
            counter_points=request.counter_points,
            evidence=request.evidence,
            confidence=request.confidence,
            kanban_task_id=request.kanban_task_id,
        )
        return self._turn_to_dto(turn)

    def advance_phase(
        self,
        room_id: str,
        target_phase: DebatePhase | None = None,
    ) -> DebateRoomResponse:
        """Step or advance debate phase."""
        state = self._manager.advance_phase(room_id=room_id, target_phase=target_phase)
        return self._to_response(state)

    def synthesize(
        self,
        room_id: str,
        consensus_decision: str,
        settled_subtask_ids: list[str] | None = None,
    ) -> DebateRoomResponse:
        """Leader or synthesizer concludes debate and settles subtasks."""
        state = self._manager.synthesize_and_converge(
            room_id=room_id,
            consensus_decision=consensus_decision,
            settled_subtask_ids=settled_subtask_ids,
        )
        return self._to_response(state)

    def sync_kanban_subtask(
        self,
        room_id: str,
        task_id: str,
        kanban_task_id: str,
        kanban_status: str | None = None,
    ) -> DebateSubtaskDTO:
        """Synchronize subtask status and kanban card id."""
        status = DebateKanbanBridge.to_debate_status(kanban_status) if kanban_status else None
        room = self._manager.get_room(room_id)
        if not room:
            raise KeyError(f"Debate room not found: {room_id}")
        current_sub = next((s for s in room.subtasks if s.task_id == task_id), None)
        if not current_sub:
            raise KeyError(f"Subtask not found: {task_id}")

        final_status = status if status is not None else current_sub.status
        updated = self._manager.update_subtask_status(
            room_id=room_id,
            task_id=task_id,
            status=final_status,
            kanban_task_id=kanban_task_id,
        )
        return self._subtask_to_dto(updated)

    def delete_room(self, room_id: str) -> bool:
        """Delete room."""
        return self._manager.cleanup_room(room_id)

    def cleanup_chat(self, chat_id: str) -> int:
        """Evict all rooms for a chat."""
        return self._manager.cleanup_chat(chat_id)
