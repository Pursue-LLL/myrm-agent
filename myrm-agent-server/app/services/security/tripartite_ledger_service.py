"""Tripartite Isolation & Immutable Audit Ledger Service.

[INPUT]
- AppendAuditRecordRequest, AuditQueryRequest, ActionSemanticExecutionRequest,
  OpsRegisterTaskRequest, OpsForceStopRequest.

[OUTPUT]
- AuditEvidenceRecordDto, VerifyLedgerResponse, AuditQueryResponse,
  ActionSemanticExecutionResponse, OpsTelemetryDto, OpsForceStopResponse.

[POS]
- Server security service. Wraps harness TripartiteAuditLedger, ActionSemanticsGuard,
  and ZeroKnowledgeOpsController.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.tripartite_ledger import (
    ActionExecutionResult,
    ActionSemanticMode,
    ActionSemanticsGuard,
    AuditEvidenceRecord,
    AuditLedgerVerificationResult,
    OpsTelemetryRecord,
    TripartiteAuditLedger,
    ZeroKnowledgeOpsController,
)

from app.schemas.tripartite_ledger import (
    ActionSemanticExecutionRequest,
    ActionSemanticExecutionResponse,
    AppendAuditRecordRequest,
    AuditEvidenceRecordDto,
    AuditQueryRequest,
    AuditQueryResponse,
    OpsForceStopRequest,
    OpsForceStopResponse,
    OpsRegisterTaskRequest,
    OpsTelemetryDto,
    VerifyLedgerResponse,
)

logger = logging.getLogger(__name__)


def _record_to_dto(record: AuditEvidenceRecord) -> AuditEvidenceRecordDto:
    """Convert harness AuditEvidenceRecord into Pydantic DTO."""
    return AuditEvidenceRecordDto(
        record_id=record.record_id,
        sequence_number=record.sequence_number,
        prev_hash=record.prev_hash,
        record_hash=record.record_hash,
        who_user_id=record.who_user_id,
        who_agent_id=record.who_agent_id,
        when_timestamp=record.when_timestamp,
        rule_version_hash=record.rule_version_hash,
        tool_name=record.tool_name,
        tool_call_args_hash=record.tool_call_args_hash,
        sanitized_args_snapshot=dict(record.sanitized_args_snapshot),
        connector_source=record.connector_source,
        connector_scope=record.connector_scope,
        authorized_parameters_hash=record.authorized_parameters_hash,
        reconcile_receipt=record.reconcile_receipt,
    )


def _telemetry_to_dto(record: OpsTelemetryRecord) -> OpsTelemetryDto:
    """Convert harness OpsTelemetryRecord into Pydantic DTO."""
    return OpsTelemetryDto(
        task_id=record.task_id,
        agent_id=record.agent_id,
        runtime_ms=record.runtime_ms,
        memory_bytes=record.memory_bytes,
        state=record.state,
    )


class TripartiteLedgerService:
    """Service managing tripartite records, action semantics, and ops telemetry."""

    def __init__(self) -> None:
        self._ledger = TripartiteAuditLedger()
        self._guard = ActionSemanticsGuard(self._ledger)
        self._ops = ZeroKnowledgeOpsController()

    @property
    def ledger(self) -> TripartiteAuditLedger:
        """Underlying audit ledger instance."""
        return self._ledger

    def append_record(self, req: AppendAuditRecordRequest) -> AuditEvidenceRecordDto:
        """Append an immutable audit evidence record to the ledger."""
        record = self._ledger.append_record(
            who_user_id=req.who_user_id,
            who_agent_id=req.who_agent_id,
            rule_version_hash=req.rule_version_hash,
            tool_name=req.tool_name,
            tool_args=req.tool_args,
            connector_source=req.connector_source,
            connector_scope=req.connector_scope,
            authorized_parameters=req.authorized_parameters,
            reconcile_receipt=req.reconcile_receipt,
            record_id=req.record_id,
            when_timestamp=req.when_timestamp,
        )
        return _record_to_dto(record)

    def verify_ledger(self) -> VerifyLedgerResponse:
        """Verify the integrity of the immutable audit ledger cryptographic hash chain."""
        result: AuditLedgerVerificationResult = self._ledger.verify_chain()
        return VerifyLedgerResponse(
            is_valid=result.is_valid,
            total_records=result.total_records,
            corrupted_record_id=result.corrupted_record_id,
            reason=result.reason,
        )

    def query_records(self, req: AuditQueryRequest) -> AuditQueryResponse:
        """Query immutable audit records matching criteria."""
        records = self._ledger.query_records(
            connector_source=req.connector_source,
            tool_name=req.tool_name,
            who_agent_id=req.who_agent_id,
            start_time=req.start_time,
            end_time=req.end_time,
        )
        dtos = [_record_to_dto(r) for r in records]
        return AuditQueryResponse(records=dtos, total_matched=len(dtos))

    def execute_semantic_action(
        self, req: ActionSemanticExecutionRequest
    ) -> ActionSemanticExecutionResponse:
        """Execute or intercept action under specified semantic mode."""
        mode = ActionSemanticMode(req.mode)

        def mock_executor() -> str:
            return f"Action executed successfully: {req.action_payload or req.tool_name}"

        result: ActionExecutionResult = self._guard.execute_action(
            mode=mode,
            tool_name=req.tool_name,
            executor=mock_executor,
            audit_record_id=req.audit_record_id,
            explicit_confirmed=req.explicit_confirmed,
        )

        return ActionSemanticExecutionResponse(
            mode=result.mode.value,
            tool_name=result.tool_name,
            executed=result.executed,
            is_simulated=result.is_simulated,
            result=result.result,
            audit_record_id=result.audit_record_id,
        )

    def register_task(self, req: OpsRegisterTaskRequest) -> OpsTelemetryDto:
        """Register task with operational telemetry."""
        self._ops.register_task(
            task_id=req.task_id,
            agent_id=req.agent_id,
            memory_bytes=req.memory_bytes,
        )
        return self.get_ops_telemetry(req.task_id)

    def get_ops_telemetry(self, task_id: str) -> OpsTelemetryDto:
        """Fetch operational telemetry without exposing business content."""
        record: OpsTelemetryRecord = self._ops.get_telemetry(task_id)
        return _telemetry_to_dto(record)

    def ops_force_stop(self, req: OpsForceStopRequest) -> OpsForceStopResponse:
        """Force-stop task via ops control without reading conversation content."""
        success = self._ops.force_stop(task_id=req.task_id, operator_id=req.operator_id)
        msg = "Task halted successfully by operations" if success else "Task not found or invalid operator"
        return OpsForceStopResponse(
            task_id=req.task_id,
            stopped=success,
            message=msg,
        )


_service_instance: TripartiteLedgerService | None = None


def get_tripartite_ledger_service() -> TripartiteLedgerService:
    """Obtain or initialize the singleton TripartiteLedgerService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TripartiteLedgerService()
    return _service_instance
