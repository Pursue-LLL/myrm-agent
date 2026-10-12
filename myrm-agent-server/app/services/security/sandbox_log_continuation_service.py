"""Service layer for Sandbox Log Redaction and Execution Continuation Audit.

[INPUT]
- RedactLogRequest, RegisterRunRequest, HeartbeatReportRequest, ContinuationAuditRequest.

[OUTPUT]
- RedactLogResponse, RegisterRunResponse, HeartbeatReportResponse, ContinuationAuditResponse.

[POS]
- Server service wrapping harness log redactor and continuation audit engine.
"""

from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.core.security.sandbox_log_continuation import (
    ExecutionContinuationAuditEngine,
    HeartbeatSignal,
    SandboxLogRedactor,
)

from app.schemas.sandbox_log_continuation import (
    ContinuationAuditRequest,
    ContinuationAuditResponse,
    HeartbeatReportRequest,
    HeartbeatReportResponse,
    RedactLogRequest,
    RedactLogResponse,
    RegisterRunRequest,
    RegisterRunResponse,
)

logger = logging.getLogger(__name__)


class SandboxLogContinuationService:
    """Orchestrates sandbox log privacy masking and execution continuation reconciliation."""

    def __init__(self) -> None:
        self._redactor = SandboxLogRedactor()
        self._audit_engine = ExecutionContinuationAuditEngine()

    def redact_logs(self, request: RedactLogRequest) -> RedactLogResponse:
        """Sanitize raw logs and commands to eliminate credentials and secret exposures."""
        result = self._redactor.redact_text(request.raw_text)

        redacted_cmd: str | None = None
        redacted_args: list[str] = []
        if request.command is not None:
            redacted_cmd, redacted_args = self._redactor.redact_command(
                request.command, request.command_args
            )

        return RedactLogResponse(
            original_length=result.original_length,
            redacted_text=result.redacted_text,
            redaction_count=result.redaction_count,
            categories_redacted=[cat.value for cat in result.categories_redacted],
            redacted_command=redacted_cmd,
            redacted_command_args=redacted_args,
        )

    def register_run(self, request: RegisterRunRequest) -> RegisterRunResponse:
        """Register an active execution run for audit tracking."""
        record = self._audit_engine.register_run(
            run_id=request.run_id,
            task_id=request.task_id,
            assignee_agent_id=request.assignee_agent_id,
            is_terminal=request.is_terminal,
        )
        return RegisterRunResponse(
            run_id=record.run_id,
            task_id=record.task_id,
            assignee_agent_id=record.assignee_agent_id,
            is_terminal=record.is_terminal,
            started_at=record.started_at,
        )

    def report_heartbeat(
        self, request: HeartbeatReportRequest
    ) -> HeartbeatReportResponse:
        """Record runner heartbeat and update activity status."""
        status_lit: Literal[
            "running", "idle", "busy", "terminating", "completed", "failed"
        ] = request.status
        signal = HeartbeatSignal(
            run_id=request.run_id,
            timestamp=request.timestamp,
            seq=request.seq,
            status=status_lit,
            metadata=request.metadata,
        )
        success = self._audit_engine.record_heartbeat(signal)
        return HeartbeatReportResponse(
            success=success,
            run_id=request.run_id,
            seq=request.seq,
            status=request.status,
        )

    def audit_continuation(
        self, request: ContinuationAuditRequest
    ) -> ContinuationAuditResponse:
        """Verify task continuity, prevent split-brain runs, and detect stale heartbeats."""
        verdict = self._audit_engine.audit_continuation(
            task_id=request.task_id,
            requesting_agent_id=request.requesting_agent_id,
            proposed_run_id=request.proposed_run_id,
            resume_source_run_id=request.resume_source_run_id,
            max_heartbeat_gap_seconds=request.max_heartbeat_gap_seconds,
        )
        return ContinuationAuditResponse(
            is_resumable=verdict.is_resumable,
            status=verdict.status.value,
            task_id=verdict.task_id,
            proposed_run_id=verdict.proposed_run_id,
            resume_source_run_id=verdict.resume_source_run_id,
            reconciliation_reason=verdict.reconciliation_reason,
            last_heartbeat_age_sec=verdict.last_heartbeat_age_sec,
        )


_GLOBAL_SERVICE: SandboxLogContinuationService | None = None


def get_sandbox_log_continuation_service() -> SandboxLogContinuationService:
    """FastAPI dependency injection provider for SandboxLogContinuationService."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = SandboxLogContinuationService()
    return _GLOBAL_SERVICE
