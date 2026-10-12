"""Unit tests for SandboxLogContinuationService.

[INPUT]
- RedactLogRequest, RegisterRunRequest, HeartbeatReportRequest, ContinuationAuditRequest.

[OUTPUT]
- Verified behavior of service layer for log redaction, run registration, heartbeat, and audits.

[POS]
- Server unit test layer for sandbox log privacy and continuation reconciliation.
"""

from __future__ import annotations

import time

from app.schemas.sandbox_log_continuation import (
    ContinuationAuditRequest,
    HeartbeatReportRequest,
    RedactLogRequest,
    RegisterRunRequest,
)
from app.services.security.sandbox_log_continuation_service import (
    SandboxLogContinuationService,
)


def test_service_redact_logs() -> None:
    service = SandboxLogContinuationService()
    req = RedactLogRequest(
        raw_text="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.xyz sk-1234567890abcdef12345678",
        command="curl -H 'Authorization: Bearer my_secret_token_1234' https://api.example.com",
        command_args=["--token=sk-99999999999999999999"],
    )
    res = service.redact_logs(req)

    assert res.redaction_count >= 2
    assert "sk-1234567890abcdef12345678" not in res.redacted_text
    assert "[REDACTED_API_KEY]" in res.redacted_text
    assert res.redacted_command is not None
    assert "my_secret_token_1234" not in res.redacted_command
    assert len(res.redacted_command_args) == 1
    assert "sk-99999999999999999999" not in res.redacted_command_args[0]


def test_service_run_lifecycle_and_heartbeat() -> None:
    service = SandboxLogContinuationService()

    # 1. Register Run
    reg_req = RegisterRunRequest(
        run_id="run-srv-01",
        task_id="task-srv-01",
        assignee_agent_id="agent-worker-1",
        is_terminal=False,
    )
    reg_res = service.register_run(reg_req)
    assert reg_res.run_id == "run-srv-01"
    assert reg_res.task_id == "task-srv-01"
    assert reg_res.is_terminal is False

    # 2. Heartbeat report
    hb_req = HeartbeatReportRequest(
        run_id="run-srv-01",
        timestamp=time.time(),
        seq=1,
        status="running",
        metadata={"cpu": "12%"},
    )
    hb_res = service.report_heartbeat(hb_req)
    assert hb_res.success is True
    assert hb_res.run_id == "run-srv-01"
    assert hb_res.seq == 1


def test_service_audit_continuation_scenarios() -> None:
    service = SandboxLogContinuationService()
    now = time.time()

    service.register_run(
        RegisterRunRequest(
            run_id="run-orig",
            task_id="task-audit-1",
            assignee_agent_id="agent-owner",
        )
    )
    service.report_heartbeat(
        HeartbeatReportRequest(
            run_id="run-orig",
            timestamp=now,
            seq=1,
            status="running",
        )
    )

    # 1. Valid resume
    audit_ok = service.audit_continuation(
        ContinuationAuditRequest(
            task_id="task-audit-1",
            requesting_agent_id="agent-owner",
            proposed_run_id="run-resumed",
            resume_source_run_id="run-orig",
            max_heartbeat_gap_seconds=120.0,
        )
    )
    assert audit_ok.is_resumable is True
    assert audit_ok.status == "VALID"

    # 2. Ownership mismatch
    audit_mismatch = service.audit_continuation(
        ContinuationAuditRequest(
            task_id="task-audit-1",
            requesting_agent_id="agent-other",
            proposed_run_id="run-resumed",
            resume_source_run_id="run-orig",
        )
    )
    assert audit_mismatch.is_resumable is False
    assert audit_mismatch.status == "OWNERSHIP_MISMATCH"

    # 3. Missing origin run
    audit_missing = service.audit_continuation(
        ContinuationAuditRequest(
            task_id="task-audit-1",
            requesting_agent_id="agent-owner",
            proposed_run_id="run-resumed",
            resume_source_run_id="run-nonexistent",
        )
    )
    assert audit_missing.is_resumable is False
    assert audit_missing.status == "MISSING_ORIGIN_RUN"
