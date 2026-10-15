# -*- coding: utf-8 -*-
"""Service managing subagent live transcripts, persistent delegation ledger, and smart approvals.

High-performance, strictly-typed bridge between harness orchestrator and API layer.
No Any types.
"""

from threading import Lock

from app.schemas.delegation_transcript import (
    ConsumeApprovalResponse,
    CreateDelegationTaskRequest,
    DelegationTaskRecordDTO,
    EmitTranscriptEventRequest,
    EvaluateCommandApprovalRequest,
    MoAReasoningAllocationRequest,
    MoAReasoningAllocationResponse,
    RecoverOrphansResponse,
    ResolveApprovalRequest,
    SaveCheckpointRequest,
    SmartApprovalRequestDTO,
    SmartApprovalResolutionDTO,
    SubagentTranscriptEventDTO,
    UpdateDelegationStatusRequest,
)
from myrm_agent_harness.agent.sub_agents.live_transcript import (
    ApprovalDecision,
    MoAReasoningEffortGovernor,
    PersistentDelegationLedger,
    ReasoningEffortLevel,
    SmartApprovalGate,
    SubagentLiveTranscriptEmitter,
    TaskDelegationStatus,
    TranscriptEventKind,
)


class DelegationTranscriptService:
    """Singleton service for live transcripts, persistent tasks, and smart approvals."""

    _instance: "DelegationTranscriptService | None" = None
    _init_lock = Lock()

    def __new__(cls) -> "DelegationTranscriptService":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._emitter = SubagentLiveTranscriptEmitter()
                cls._instance._ledger = PersistentDelegationLedger()
                cls._instance._gate = SmartApprovalGate()
                cls._instance._governor = MoAReasoningEffortGovernor()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance for test isolation."""
        with cls._init_lock:
            cls._instance = None

    def create_task(self, req: CreateDelegationTaskRequest) -> DelegationTaskRecordDTO:
        effort_enum = ReasoningEffortLevel(req.reasoning_effort.lower())
        record = self._ledger.register_task(
            task_id=req.task_id,
            session_id=req.session_id,
            subagent_id=req.subagent_id,
            role=req.role,
            prompt=req.prompt,
            reasoning_effort=effort_enum,
        )
        return DelegationTaskRecordDTO(**record.model_dump())

    def get_task(self, task_id: str) -> DelegationTaskRecordDTO | None:
        record = self._ledger.get_task(task_id)
        if not record:
            return None
        return DelegationTaskRecordDTO(**record.model_dump())

    def list_tasks(
        self,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[DelegationTaskRecordDTO]:
        status_enum = TaskDelegationStatus(status) if status else None
        records = self._ledger.list_tasks(session_id=session_id, status=status_enum)
        return [DelegationTaskRecordDTO(**r.model_dump()) for r in records]

    def update_task_status(
        self,
        task_id: str,
        req: UpdateDelegationStatusRequest,
    ) -> DelegationTaskRecordDTO | None:
        status_enum = TaskDelegationStatus(req.status.lower())
        record = self._ledger.update_status(
            task_id=task_id,
            status=status_enum,
            summary=req.summary,
            error_message=req.error_message,
        )
        if not record:
            return None
        return DelegationTaskRecordDTO(**record.model_dump())

    def save_checkpoint(
        self,
        task_id: str,
        req: SaveCheckpointRequest,
    ) -> DelegationTaskRecordDTO | None:
        record = self._ledger.save_checkpoint(
            task_id=task_id,
            checkpoint_step=req.checkpoint_step,
            artifacts=req.artifacts,
        )
        if not record:
            return None
        return DelegationTaskRecordDTO(**record.model_dump())

    def emit_event(
        self,
        task_id: str,
        req: EmitTranscriptEventRequest,
    ) -> SubagentTranscriptEventDTO:
        kind_enum = TranscriptEventKind(req.kind.lower())
        event = self._emitter.emit(
            task_id=task_id,
            subagent_id=req.subagent_id,
            kind=kind_enum,
            human_readable=req.human_readable,
            payload=req.payload,
        )
        return SubagentTranscriptEventDTO(**event.model_dump())

    def get_events(
        self,
        task_id: str,
        after_seq: int = 0,
        limit: int | None = None,
    ) -> list[SubagentTranscriptEventDTO]:
        events = self._emitter.get_events(task_id=task_id, after_seq=after_seq, limit=limit)
        return [SubagentTranscriptEventDTO(**e.model_dump()) for e in events]

    def evaluate_command(
        self,
        req: EvaluateCommandApprovalRequest,
    ) -> SmartApprovalRequestDTO:
        request = self._gate.evaluate_command(
            task_id=req.task_id,
            subagent_id=req.subagent_id,
            command=req.command,
        )
        return SmartApprovalRequestDTO(**request.model_dump())

    def resolve_approval(
        self,
        approval_id: str,
        req: ResolveApprovalRequest,
    ) -> SmartApprovalResolutionDTO | None:
        decision_enum = ApprovalDecision(req.decision.lower())
        res = self._gate.resolve_approval(
            approval_id=approval_id,
            decision=decision_enum,
            deny_reason=req.deny_reason,
        )
        if not res:
            return None
        return SmartApprovalResolutionDTO(**res.model_dump())

    def consume_approval(self, approval_id: str) -> ConsumeApprovalResponse:
        success = self._gate.consume_approval(approval_id)
        msg = (
            "Approval consumed successfully."
            if success
            else "Approval consumption failed (already consumed or not approved)."
        )
        return ConsumeApprovalResponse(approval_id=approval_id, consumed=success, message=msg)

    def recover_orphans(self) -> RecoverOrphansResponse:
        recovered = self._ledger.recover_orphaned_tasks()
        return RecoverOrphansResponse(
            recovered_count=len(recovered),
            recovered_tasks=[DelegationTaskRecordDTO(**r.model_dump()) for r in recovered],
        )

    def allocate_reasoning(
        self,
        req: MoAReasoningAllocationRequest,
    ) -> MoAReasoningAllocationResponse:
        effort = self._governor.resolve_effort(req.role)
        budget = self._governor.get_token_budget(effort)
        return MoAReasoningAllocationResponse(
            role=req.role,
            effort=effort.value,
            token_budget=budget,
        )


def get_delegation_transcript_service() -> DelegationTranscriptService:
    """Dependency injection helper."""
    return DelegationTranscriptService()
