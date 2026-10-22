"""Service layer managing Durable Agent Teams sessions and orchestration engines.

[INPUT]
- app.schemas.agent_teams::(SpawnTeammateRequest, CreateTeamTaskRequest,
                            UpdateTeamTaskRequest, ClaimTeamTaskRequest,
                            CompleteTeamTaskRequest, SendTeamMessageRequest,
                            TeamMemberResponse, TeamTaskResponse, TeamMessageResponse,
                            DrainInboxResponse, TeamProjectionResponse)
- myrm_agent_harness.agent.sub_agents.teams::(DurableAgentTeamEngine, DeliveryMode,
                                              CASConflictError, TaskBlockedError,
                                              TaskDependencyCycleError, TeamTaskStatus)

[OUTPUT]
- AgentTeamsService: singleton service managing team lifecycles, CAS tasks, and mailboxes
- get_agent_teams_service: accessor function

[POS]
Business service layer for Topic 12 #28 DurableAgentTeamsPeerMailboxAndSharedTaskDagKanban.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.sub_agents.teams import (
    DeliveryMode,
    DurableAgentTeamEngine,
    TeamMemberSnapshot,
    TeamMessageSnapshot,
    TeamTaskStatus,
    TeamTaskView,
)

from app.schemas.agent_teams import (
    ClaimTeamTaskRequest,
    CompleteTeamTaskRequest,
    CreateTeamTaskRequest,
    DeliveryModeEnum,
    DrainInboxResponse,
    SendTeamMessageRequest,
    SpawnTeammateRequest,
    TeamMemberPhaseEnum,
    TeamMemberResponse,
    TeamMemberRoleEnum,
    TeamMessageResponse,
    TeamProjectionResponse,
    TeamTaskResponse,
    TeamTaskStatusEnum,
    UpdateTeamTaskRequest,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_SERVICE_INSTANCE: AgentTeamsService | None = None


class AgentTeamsService:
    """Manages active durable agent teams and their execution states."""

    def __init__(self) -> None:
        self._teams: dict[str, DurableAgentTeamEngine] = {}

    def get_or_create_team(
        self,
        team_id: str,
        workspace_path: str | None = None,
    ) -> DurableAgentTeamEngine:
        """Get existing team engine or initialize a new implicit root lead team."""
        engine = self._teams.get(team_id)
        if engine is None:
            engine = DurableAgentTeamEngine(team_id=team_id, workspace_path=workspace_path)
            self._teams[team_id] = engine
        return engine

    # -------------------------------------------------------------------------
    # Roster Operations
    # -------------------------------------------------------------------------

    def spawn_teammate(
        self,
        team_id: str,
        request: SpawnTeammateRequest,
        workspace_path: str | None = None,
    ) -> TeamMemberResponse:
        engine = self.get_or_create_team(team_id, workspace_path)
        member = engine.spawn_teammate(
            name=request.name,
            description=request.description,
            provider=request.provider,
            context=request.context,
        )
        return self._to_member_response(member)

    def fail_teammate(
        self,
        team_id: str,
        name: str,
        error: str,
    ) -> TeamMemberResponse:
        engine = self.get_or_create_team(team_id)
        member = engine.fail_teammate(name=name, error=error)
        return self._to_member_response(member)

    def list_members(self, team_id: str) -> list[TeamMemberResponse]:
        engine = self.get_or_create_team(team_id)
        return [self._to_member_response(m) for m in engine.list_members()]

    # -------------------------------------------------------------------------
    # Shared CAS Task Board Operations
    # -------------------------------------------------------------------------

    def create_task(
        self,
        team_id: str,
        request: CreateTeamTaskRequest,
        workspace_path: str | None = None,
    ) -> TeamTaskResponse:
        engine = self.get_or_create_team(team_id, workspace_path)
        view = engine.create_task(
            subject=request.subject,
            description=request.description,
            blocked_by=request.blocked_by,
            write_scopes=request.write_scopes,
            owner_name=request.owner_name,
        )
        return self._to_task_response(view)

    def claim_task(
        self,
        team_id: str,
        task_id: str,
        request: ClaimTeamTaskRequest,
    ) -> TeamTaskResponse:
        engine = self.get_or_create_team(team_id)
        view = engine.claim_task(
            task_id=task_id,
            expected_revision=request.expected_revision,
            owner_name=request.owner_name,
        )
        return self._to_task_response(view)

    def complete_task(
        self,
        team_id: str,
        task_id: str,
        request: CompleteTeamTaskRequest,
    ) -> TeamTaskResponse:
        engine = self.get_or_create_team(team_id)
        view = engine.complete_task(
            task_id=task_id,
            expected_revision=request.expected_revision,
        )
        return self._to_task_response(view)

    def update_task(
        self,
        team_id: str,
        task_id: str,
        request: UpdateTeamTaskRequest,
    ) -> TeamTaskResponse:
        engine = self.get_or_create_team(team_id)
        status = TeamTaskStatus(request.status.value) if request.status else None
        view = engine.update_task(
            task_id=task_id,
            expected_revision=request.expected_revision,
            subject=request.subject,
            description=request.description,
            status=status,
            owner_name=request.owner_name,
            blocked_by=request.blocked_by,
            write_scopes=request.write_scopes,
        )
        return self._to_task_response(view)

    def list_tasks(self, team_id: str, include_deleted: bool = False) -> list[TeamTaskResponse]:
        engine = self.get_or_create_team(team_id)
        return [self._to_task_response(t) for t in engine.list_tasks(include_deleted=include_deleted)]

    def get_task(self, team_id: str, task_id: str) -> TeamTaskResponse:
        engine = self.get_or_create_team(team_id)
        view = engine.get_task(task_id=task_id)
        return self._to_task_response(view)

    # -------------------------------------------------------------------------
    # Peer Mailbox Operations
    # -------------------------------------------------------------------------

    def send_message(
        self,
        team_id: str,
        request: SendTeamMessageRequest,
        workspace_path: str | None = None,
    ) -> TeamMessageResponse:
        engine = self.get_or_create_team(team_id, workspace_path)
        mode = DeliveryMode.WAKING if request.mode == DeliveryModeEnum.WAKING else DeliveryMode.QUIET
        snapshot = engine.send_peer_message(
            sender_name=request.sender_name,
            target_name=request.target_name,
            content=request.content,
            mode=mode,
        )
        return self._to_message_response(snapshot)

    def drain_inbox(self, team_id: str, member_name: str) -> DrainInboxResponse:
        engine = self.get_or_create_team(team_id)
        messages = engine.drain_inbox(member_name=member_name)
        return DrainInboxResponse(
            member_name=member_name,
            messages=[self._to_message_response(m) for m in messages],
        )

    def list_message_history(self, team_id: str, limit: int = 100) -> list[dict[str, object]]:
        engine = self.get_or_create_team(team_id)
        return engine.list_message_history(limit=limit)

    # -------------------------------------------------------------------------
    # Projection & Change Observation
    # -------------------------------------------------------------------------

    def get_projection(self, team_id: str) -> TeamProjectionResponse:
        engine = self.get_or_create_team(team_id)
        projection = engine.get_projection()
        return TeamProjectionResponse(
            team_id=projection.team_id,
            members=[self._to_member_response(m) for m in projection.members],
            tasks=[self._to_task_response(t) for t in projection.tasks],
            failure=projection.failure,
        )

    async def wait_for_change(self, team_id: str, timeout_sec: float = 10.0) -> bool:
        engine = self.get_or_create_team(team_id)
        return await engine.wait_for_change(timeout_sec=timeout_sec)

    # -------------------------------------------------------------------------
    # DTO Helpers
    # -------------------------------------------------------------------------

    def _to_member_response(self, m: TeamMemberSnapshot) -> TeamMemberResponse:
        return TeamMemberResponse(
            id=m.id,
            name=m.name,
            description=m.description,
            provider=m.provider,
            context=m.context,
            role=TeamMemberRoleEnum(m.role.value),
            phase=TeamMemberPhaseEnum(m.phase.value),
            error=m.error,
            created_at=m.created_at,
        )

    def _to_task_response(self, t: TeamTaskView) -> TeamTaskResponse:
        return TeamTaskResponse(
            id=t.id,
            revision=t.revision,
            subject=t.subject,
            description=t.description,
            status=TeamTaskStatusEnum(t.status.value),
            owner_id=t.owner_id,
            owner_name=t.owner_name,
            blocked_by=list(t.blocked_by),
            write_scopes=list(t.write_scopes),
            ready=t.ready,
            write_scope_warnings=list(t.write_scope_warnings),
        )

    def _to_message_response(self, msg: TeamMessageSnapshot) -> TeamMessageResponse:
        return TeamMessageResponse(
            id=msg.id,
            team_id=msg.team_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender_name,
            target_id=msg.target_id,
            target_name=msg.target_name,
            content=msg.content,
            mode=DeliveryModeEnum(msg.mode.value),
            created_at=msg.created_at,
            delivered=msg.delivered,
        )


def get_agent_teams_service() -> AgentTeamsService:
    """Return the singleton instance of AgentTeamsService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = AgentTeamsService()
    return _SERVICE_INSTANCE
