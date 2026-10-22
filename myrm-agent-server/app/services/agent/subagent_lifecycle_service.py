"""Service mediating Native Subagent Lifecycle Toolchain operations (Item 46).

[INPUT]
- SubagentSpawnRequest, SubagentSendInputRequest, SubagentKillRequest, SubagentWaitRequest.

[OUTPUT]
- SubagentLifecycleService managing lifecycle primitives, auditing, and status serialization.

[POS]
- Service layer for native subagent execution, steering, and containment.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.sub_agents.lifecycle_toolchain import (
    SubagentEventItem,
    SubagentInputMessage,
    SubagentLifecycleManager,
    SubagentTaskRecord,
    SubagentWaitResult,
)
from myrm_agent_harness.agent.sub_agents.lifecycle_toolchain import (
    SubagentSpawnRequest as HarnessSpawnRequest,
)
from myrm_agent_harness.agent.sub_agents.lifecycle_toolchain import (
    SubagentStatusEnum as HarnessStatusEnum,
)

from app.schemas.subagent_lifecycle import (
    SubagentEventItemDTO,
    SubagentInputMessageDTO,
    SubagentKillRequest,
    SubagentListResponseDTO,
    SubagentSendInputRequest,
    SubagentSpawnRequest,
    SubagentStatusEnum,
    SubagentTaskItemDTO,
    SubagentWaitRequest,
    SubagentWaitResponseDTO,
)

logger = logging.getLogger(__name__)


def _event_to_dto(event: SubagentEventItem) -> SubagentEventItemDTO:
    return SubagentEventItemDTO(
        event_id=event.event_id,
        event_type=event.event_type,
        subagent_id=event.subagent_id,
        payload=dict(event.payload),
        timestamp=event.timestamp,
    )


def _input_to_dto(msg: SubagentInputMessage) -> SubagentInputMessageDTO:
    return SubagentInputMessageDTO(
        message_id=msg.message_id,
        subagent_id=msg.subagent_id,
        content=msg.content,
        sender_role=msg.sender_role,
        created_at=msg.created_at,
    )


def _record_to_dto(record: SubagentTaskRecord) -> SubagentTaskItemDTO:
    return SubagentTaskItemDTO(
        subagent_id=record.subagent_id,
        parent_session_id=record.parent_session_id,
        task_prompt=record.task_prompt,
        agent_profile=record.agent_profile,
        tools_whitelist=list(record.tools_whitelist),
        status=SubagentStatusEnum(record.status.value),
        timeout_seconds=record.timeout_seconds,
        created_at=record.created_at,
        started_at=record.started_at,
        ended_at=record.ended_at,
        result_summary=record.result_summary,
        error_detail=record.error_detail,
        kill_reason=record.kill_reason,
        token_usage=record.token_usage,
        step_count=record.step_count,
        input_queue=[_input_to_dto(m) for m in record.input_queue],
        events=[_event_to_dto(e) for e in record.events],
    )


class SubagentLifecycleService:
    """Service orchestrating native subagent lifecycle primitives."""

    def __init__(self) -> None:
        self._manager = SubagentLifecycleManager()
        self._lock = threading.RLock()

    def spawn_subagent(
        self,
        chat_id: str,
        request: SubagentSpawnRequest,
    ) -> SubagentTaskItemDTO:
        """Spawn a new subagent tied to the current chat session."""
        harness_req = HarnessSpawnRequest(
            task_prompt=request.task_prompt,
            parent_session_id=chat_id,
            agent_profile=request.agent_profile,
            tools_whitelist=request.tools_whitelist,
            timeout_seconds=request.timeout_seconds,
        )
        record = self._manager.spawn(harness_req)
        logger.info(
            "Spawned subagent %s for session %s (profile=%s)",
            record.subagent_id,
            chat_id,
            request.agent_profile,
        )
        return _record_to_dto(record)

    def get_subagent(self, chat_id: str, subagent_id: str) -> SubagentTaskItemDTO:
        """Retrieve a specific subagent record verifying chat_id match."""
        record = self._manager.get_subagent(subagent_id)
        if record.parent_session_id != chat_id:
            raise KeyError(f"Subagent {subagent_id} does not belong to session {chat_id}")
        return _record_to_dto(record)

    def list_subagents(
        self,
        chat_id: str,
        status_filter: SubagentStatusEnum | None = None,
        limit: int = 50,
    ) -> SubagentListResponseDTO:
        """List subagents bound to chat session."""
        harness_status = HarnessStatusEnum(status_filter.value) if status_filter else None
        records = self._manager.list_subagents(
            parent_session_id=chat_id,
            status_filter=harness_status,
            limit=limit,
        )
        dtos = [_record_to_dto(r) for r in records]
        return SubagentListResponseDTO(tasks=dtos, total=len(dtos))

    def send_input(
        self,
        chat_id: str,
        subagent_id: str,
        request: SubagentSendInputRequest,
    ) -> SubagentInputMessageDTO:
        """Inject guidance into subagent."""
        record = self._manager.get_subagent(subagent_id)
        if record.parent_session_id != chat_id:
            raise KeyError(f"Subagent {subagent_id} does not belong to session {chat_id}")

        msg = self._manager.send_input(
            subagent_id=subagent_id,
            content=request.content,
            sender_role=request.sender_role,
        )
        return _input_to_dto(msg)

    def kill_subagent(
        self,
        chat_id: str,
        subagent_id: str,
        request: SubagentKillRequest,
    ) -> SubagentTaskItemDTO:
        """Terminate a running subagent immediately."""
        record = self._manager.get_subagent(subagent_id)
        if record.parent_session_id != chat_id:
            raise KeyError(f"Subagent {subagent_id} does not belong to session {chat_id}")

        killed = self._manager.kill(subagent_id=subagent_id, reason=request.reason)
        return _record_to_dto(killed)

    def wait_subagents(
        self,
        chat_id: str,
        request: SubagentWaitRequest,
    ) -> SubagentWaitResponseDTO:
        """Wait for multiple subagents within the session to finish."""
        # Verify ownership
        for sid in request.subagent_ids:
            rec = self._manager.get_subagent(sid)
            if rec.parent_session_id != chat_id:
                raise KeyError(f"Subagent {sid} does not belong to session {chat_id}")

        result: SubagentWaitResult = self._manager.wait(
            subagent_ids=request.subagent_ids,
            timeout_seconds=request.timeout_seconds,
        )
        return SubagentWaitResponseDTO(
            all_completed=result.all_completed,
            completed_count=result.completed_count,
            failed_count=result.failed_count,
            killed_count=result.killed_count,
            timeout_count=result.timeout_count,
            tasks=[_record_to_dto(t) for t in result.tasks],
        )

    def simulate_complete(
        self,
        chat_id: str,
        subagent_id: str,
        result_summary: str,
        token_usage: int = 1500,
        step_count: int = 4,
    ) -> SubagentTaskItemDTO:
        """Simulate task completion for verification and UI testing."""
        record = self._manager.get_subagent(subagent_id)
        if record.parent_session_id != chat_id:
            raise KeyError(f"Subagent {subagent_id} does not belong to session {chat_id}")

        completed = self._manager.complete(
            subagent_id=subagent_id,
            result_summary=result_summary,
            token_usage=token_usage,
            step_count=step_count,
        )
        return _record_to_dto(completed)

    def simulate_fail(
        self,
        chat_id: str,
        subagent_id: str,
        error_detail: str,
    ) -> SubagentTaskItemDTO:
        """Simulate task failure for testing."""
        record = self._manager.get_subagent(subagent_id)
        if record.parent_session_id != chat_id:
            raise KeyError(f"Subagent {subagent_id} does not belong to session {chat_id}")

        failed = self._manager.fail(subagent_id=subagent_id, error_detail=error_detail)
        return _record_to_dto(failed)


_SERVICE_INSTANCE: SubagentLifecycleService | None = None
_INSTANCE_LOCK = threading.Lock()


def get_subagent_lifecycle_service() -> SubagentLifecycleService:
    """Get the singleton instance of SubagentLifecycleService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        with _INSTANCE_LOCK:
            if _SERVICE_INSTANCE is None:
                _SERVICE_INSTANCE = SubagentLifecycleService()
    return _SERVICE_INSTANCE
