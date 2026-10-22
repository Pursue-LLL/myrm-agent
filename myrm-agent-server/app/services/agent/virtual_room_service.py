"""Service implementation for Multi-Human Multi-Agent Collaborative Virtual Room (Item 59).

[INPUT]
- CreateRoomRequest, JoinRoomRequest, LeaveRoomRequest, AcquireFileLockRequest,
  ReleaseFileLockRequest, CreateBorrowingGrantRequest, DelegateExecutionRequest,
  RevokeBorrowingGrantRequest, RegisterServiceRelayRequest.

[OUTPUT]
- VirtualRoomStateDTO, VirtualRoomParticipantDTO, FileBlockLeaseLockDTO,
  AgentBorrowingGrantDTO, RoomServicePortRelayDTO, VirtualRoomActivityEventDTO.

[POS]
- Server-side business service bridging Harness VirtualCoDevRoomManager to REST APIs.
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.agent.sub_agents.virtual_room import (
    AgentBorrowingGrant,
    BorrowingGrantStatusEnum,
    FileBlockLeaseLock,
    LockScopeEnum,
    ParticipantRoleEnum,
    RoomServicePortRelay,
    VirtualCoDevRoomManager,
    VirtualRoomActivityEvent,
    VirtualRoomParticipant,
    VirtualRoomState,
)

from app.schemas.virtual_room import (
    AcquireFileLockRequest,
    AgentBorrowingGrantDTO,
    BorrowingGrantStatusDTOEnum,
    CreateBorrowingGrantRequest,
    CreateRoomRequest,
    DelegateExecutionRequest,
    FileBlockLeaseLockDTO,
    JoinRoomRequest,
    LeaveRoomRequest,
    LockScopeDTOEnum,
    ParticipantRoleDTOEnum,
    RegisterServiceRelayRequest,
    ReleaseFileLockRequest,
    RevokeBorrowingGrantRequest,
    RoomServicePortRelayDTO,
    VirtualRoomActivityEventDTO,
    VirtualRoomParticipantDTO,
    VirtualRoomStateDTO,
)

logger: Final = logging.getLogger(__name__)


def _map_role_dto_to_harness(role: ParticipantRoleDTOEnum) -> ParticipantRoleEnum:
    match role:
        case ParticipantRoleDTOEnum.HUMAN_DEV:
            return ParticipantRoleEnum.HUMAN_DEV
        case ParticipantRoleDTOEnum.AGENT_WORKER:
            return ParticipantRoleEnum.AGENT_WORKER
        case ParticipantRoleDTOEnum.AGENT_REVIEWER:
            return ParticipantRoleEnum.AGENT_REVIEWER
        case ParticipantRoleDTOEnum.AGENT_ARCHITECT:
            return ParticipantRoleEnum.AGENT_ARCHITECT


def _map_role_harness_to_dto(role: ParticipantRoleEnum) -> ParticipantRoleDTOEnum:
    match role:
        case ParticipantRoleEnum.HUMAN_DEV:
            return ParticipantRoleDTOEnum.HUMAN_DEV
        case ParticipantRoleEnum.AGENT_WORKER:
            return ParticipantRoleDTOEnum.AGENT_WORKER
        case ParticipantRoleEnum.AGENT_REVIEWER:
            return ParticipantRoleDTOEnum.AGENT_REVIEWER
        case ParticipantRoleEnum.AGENT_ARCHITECT:
            return ParticipantRoleDTOEnum.AGENT_ARCHITECT


def _map_scope_dto_to_harness(scope: LockScopeDTOEnum) -> LockScopeEnum:
    match scope:
        case LockScopeDTOEnum.FILE_FULL:
            return LockScopeEnum.FILE_FULL
        case LockScopeDTOEnum.LINE_RANGE:
            return LockScopeEnum.LINE_RANGE
        case LockScopeDTOEnum.AST_BLOCK:
            return LockScopeEnum.AST_BLOCK


def _map_scope_harness_to_dto(scope: LockScopeEnum) -> LockScopeDTOEnum:
    match scope:
        case LockScopeEnum.FILE_FULL:
            return LockScopeDTOEnum.FILE_FULL
        case LockScopeEnum.LINE_RANGE:
            return LockScopeDTOEnum.LINE_RANGE
        case LockScopeEnum.AST_BLOCK:
            return LockScopeDTOEnum.AST_BLOCK


def _map_grant_status_harness_to_dto(
    status: BorrowingGrantStatusEnum,
) -> BorrowingGrantStatusDTOEnum:
    match status:
        case BorrowingGrantStatusEnum.ACTIVE:
            return BorrowingGrantStatusDTOEnum.ACTIVE
        case BorrowingGrantStatusEnum.REVOKED:
            return BorrowingGrantStatusDTOEnum.REVOKED
        case BorrowingGrantStatusEnum.EXPIRED:
            return BorrowingGrantStatusDTOEnum.EXPIRED
        case BorrowingGrantStatusEnum.EXHAUSTED:
            return BorrowingGrantStatusDTOEnum.EXHAUSTED


def _map_participant_to_dto(p: VirtualRoomParticipant) -> VirtualRoomParticipantDTO:
    return VirtualRoomParticipantDTO(
        participant_id=p.participant_id,
        name=p.name,
        role=_map_role_harness_to_dto(p.role),
        local_identity_bound=p.local_identity_bound,
        is_active=p.is_active,
        joined_at=p.joined_at,
    )


def _map_lock_to_dto(lk: FileBlockLeaseLock) -> FileBlockLeaseLockDTO:
    return FileBlockLeaseLockDTO(
        lock_id=lk.lock_id,
        file_path=lk.file_path,
        holder_id=lk.holder_id,
        holder_role=_map_role_harness_to_dto(lk.holder_role),
        scope=_map_scope_harness_to_dto(lk.scope),
        start_line=lk.start_line,
        end_line=lk.end_line,
        acquired_at=lk.acquired_at,
        expires_at=lk.expires_at,
        ttl_seconds=lk.ttl_seconds,
    )


def _map_grant_to_dto(g: AgentBorrowingGrant) -> AgentBorrowingGrantDTO:
    return AgentBorrowingGrantDTO(
        grant_id=g.grant_id,
        room_id=g.room_id,
        owner_id=g.owner_id,
        borrower_id=g.borrower_id,
        target_agent_model=g.target_agent_model,
        quota_tokens=g.quota_tokens,
        used_tokens=g.used_tokens,
        status=_map_grant_status_harness_to_dto(g.status),
        expires_at=g.expires_at,
    )


def _map_relay_to_dto(r: RoomServicePortRelay) -> RoomServicePortRelayDTO:
    return RoomServicePortRelayDTO(
        relay_id=r.relay_id,
        room_id=r.room_id,
        service_name=r.service_name,
        port=r.port,
        live_preview_url=r.live_preview_url,
        launched_by_id=r.launched_by_id,
        is_healthy=r.is_healthy,
        created_at=r.created_at,
    )


def _map_event_to_dto(e: VirtualRoomActivityEvent) -> VirtualRoomActivityEventDTO:
    return VirtualRoomActivityEventDTO(
        event_id=e.event_id,
        room_id=e.room_id,
        actor_id=e.actor_id,
        event_type=e.event_type,
        details=dict(e.details),
        timestamp=e.timestamp,
    )


def _map_state_to_dto(s: VirtualRoomState) -> VirtualRoomStateDTO:
    return VirtualRoomStateDTO(
        room_id=s.room_id,
        name=s.name,
        participants=[_map_participant_to_dto(p) for p in s.participants],
        active_locks=[_map_lock_to_dto(lk) for lk in s.active_locks],
        borrowing_grants=[_map_grant_to_dto(g) for g in s.borrowing_grants],
        service_relays=[_map_relay_to_dto(r) for r in s.service_relays],
        created_at=s.created_at,
        last_activity_at=s.last_activity_at,
    )


class VirtualRoomService:
    """Coordinates collaborative virtual room workspaces, VFS lock engines, and relays."""

    def __init__(self) -> None:
        self._manager = VirtualCoDevRoomManager()

    def create_room(self, req: CreateRoomRequest) -> VirtualRoomStateDTO:
        state = self._manager.create_room(room_id=req.room_id, name=req.name)
        return _map_state_to_dto(state)

    def join_room(self, room_id: str, req: JoinRoomRequest) -> VirtualRoomParticipantDTO:
        harness_role = _map_role_dto_to_harness(req.role)
        participant = self._manager.join_room(
            room_id=room_id,
            participant_id=req.participant_id,
            name=req.name,
            role=harness_role,
            local_identity_bound=req.local_identity_bound,
        )
        return _map_participant_to_dto(participant)

    def leave_room(self, room_id: str, req: LeaveRoomRequest) -> bool:
        return self._manager.leave_room(room_id=room_id, participant_id=req.participant_id)

    def get_room_state(self, room_id: str) -> VirtualRoomStateDTO:
        state = self._manager.get_room_state(room_id)
        return _map_state_to_dto(state)

    def list_rooms(self) -> list[VirtualRoomStateDTO]:
        states = self._manager.list_rooms()
        return [_map_state_to_dto(s) for s in states]

    def acquire_file_lock(self, req: AcquireFileLockRequest) -> FileBlockLeaseLockDTO:
        harness_role = _map_role_dto_to_harness(req.holder_role)
        harness_scope = _map_scope_dto_to_harness(req.scope)
        lock = self._manager.lock_engine.acquire_lock(
            file_path=req.file_path,
            holder_id=req.holder_id,
            holder_role=harness_role,
            start_line=req.start_line,
            end_line=req.end_line,
            scope=harness_scope,
            ttl_seconds=req.ttl_seconds,
        )
        return _map_lock_to_dto(lock)

    def release_file_lock(self, req: ReleaseFileLockRequest) -> bool:
        return self._manager.lock_engine.release_lock(
            lock_id=req.lock_id, holder_id=req.holder_id
        )

    def list_active_locks(self, file_path: str | None = None) -> list[FileBlockLeaseLockDTO]:
        locks = self._manager.lock_engine.list_active_locks(file_path=file_path)
        return [_map_lock_to_dto(lk) for lk in locks]

    def create_borrowing_grant(self, req: CreateBorrowingGrantRequest) -> AgentBorrowingGrantDTO:
        grant = self._manager.borrowing_gateway.create_grant(
            room_id=req.room_id,
            owner_id=req.owner_id,
            borrower_id=req.borrower_id,
            target_agent_model=req.target_agent_model,
            quota_tokens=req.quota_tokens,
            ttl_seconds=req.ttl_seconds,
        )
        return _map_grant_to_dto(grant)

    def delegate_execution(
        self, req: DelegateExecutionRequest
    ) -> tuple[bool, str, int]:
        return self._manager.borrowing_gateway.delegate_execution(
            grant_id=req.grant_id,
            borrower_id=req.borrower_id,
            prompt=req.prompt,
            token_cost=req.token_cost,
        )

    def revoke_borrowing_grant(self, req: RevokeBorrowingGrantRequest) -> AgentBorrowingGrantDTO:
        grant = self._manager.borrowing_gateway.revoke_grant(
            grant_id=req.grant_id, owner_id=req.owner_id
        )
        return _map_grant_to_dto(grant)

    def register_service_relay(self, req: RegisterServiceRelayRequest) -> RoomServicePortRelayDTO:
        relay = self._manager.register_service_relay(
            room_id=req.room_id,
            service_name=req.service_name,
            port=req.port,
            launched_by_id=req.launched_by_id,
        )
        return _map_relay_to_dto(relay)

    def list_activity_events(self, room_id: str) -> list[VirtualRoomActivityEventDTO]:
        events = self._manager.list_activity_events(room_id)
        return [_map_event_to_dto(e) for e in events]

    def reset(self) -> None:
        self._manager.clear()


_global_virtual_room_service: VirtualRoomService | None = None


def get_virtual_room_service() -> VirtualRoomService:
    global _global_virtual_room_service
    if _global_virtual_room_service is None:
        _global_virtual_room_service = VirtualRoomService()
    return _global_virtual_room_service
