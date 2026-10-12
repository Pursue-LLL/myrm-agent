"""
[POS] tests/unit/test_scoped_approval_gate_service.py
Unit tests for ScopedApprovalGateService.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.scoped_approval_gate import (
    IssueGrantRequestDTO,
    RevokeAllRequestDTO,
    RiskEvaluationRequestDTO,
)
from app.services.security.scoped_approval_gate_service import (
    ScopedApprovalGateService,
)


@pytest.fixture
def service() -> ScopedApprovalGateService:
    return ScopedApprovalGateService()


def test_issue_grant_and_list_active(service: ScopedApprovalGateService) -> None:
    req = IssueGrantRequestDTO(
        tool_name="database_migrate",
        scope="task",
        agent_id="db-agent",
        session_id="sess-01",
        task_id="task-db-42",
    )
    lease = service.issue_grant(req)
    assert lease.grant_id.startswith("grant-")
    assert lease.tool_name == "database_migrate"
    assert lease.scope == "task"
    assert lease.use_count == 0

    active_resp = service.list_active_grants()
    assert len(active_resp.grants) == 1
    assert active_resp.grants[0].grant_id == lease.grant_id


def test_evaluate_risk_with_active_lease_and_ledger(service: ScopedApprovalGateService) -> None:
    # 1. Evaluate high risk without grant -> ask
    eval_req = RiskEvaluationRequestDTO(
        tool_name="terminal_run",
        risk_tier="high_risk_write",
        agent_id="ops-agent",
        session_id="sess-prod",
        task_id="task-run-1",
    )
    res1 = service.evaluate_risk(eval_req)
    assert res1.decision == "ask"
    assert res1.requires_hitl_prompt is True
    assert res1.matched_grant_id is None

    # 2. Issue grant
    grant_req = IssueGrantRequestDTO(
        tool_name="terminal_run",
        scope="task",
        agent_id="ops-agent",
        session_id="sess-prod",
        task_id="task-run-1",
    )
    lease = service.issue_grant(grant_req)

    # 3. Re-evaluate with active grant -> allow
    res2 = service.evaluate_risk(eval_req)
    assert res2.decision == "allow"
    assert res2.matched_grant_id == lease.grant_id
    assert res2.requires_hitl_prompt is False

    # 4. Check ledger
    ledger_resp = service.get_audit_ledger()
    assert len(ledger_resp.records) == 1
    assert ledger_resp.records[0].grant_id == lease.grant_id
    assert ledger_resp.records[0].tool_name == "terminal_run"


def test_revocation_and_metrics(service: ScopedApprovalGateService) -> None:
    g1 = service.issue_grant(
        IssueGrantRequestDTO(
            tool_name="git_push",
            scope="session",
            agent_id="git-agent",
            session_id="sess-git",
        )
    )
    g2 = service.issue_grant(
        IssueGrantRequestDTO(
            tool_name="git_tag",
            scope="session",
            agent_id="git-agent",
            session_id="sess-git",
        )
    )
    assert len(service.list_active_grants().grants) == 2
    assert g2.grant_id.startswith("grant-")

    # Revoke single
    rev1 = service.revoke_grant(g1.grant_id)
    assert rev1.success is True
    assert len(service.list_active_grants().grants) == 1

    # Revoke all
    rev_all = service.revoke_all(RevokeAllRequestDTO(session_id="sess-git"))
    assert rev_all.revoked_count == 1
    assert len(service.list_active_grants().grants) == 0

    # Metrics
    metrics = service.get_metrics()
    assert metrics.grants_issued_total == 2
    assert metrics.grants_revoked_total == 2
