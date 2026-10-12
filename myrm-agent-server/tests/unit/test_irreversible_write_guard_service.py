"""Unit tests for IrreversibleWriteGuardService."""

from __future__ import annotations

import pytest

from app.schemas.irreversible_write_guard import (
    ApproveIntentRequest,
    EmergencyKillRequest,
    InterceptToolCallRequest,
    RegisterContractRequest,
)
from app.services.security.irreversible_write_guard_service import (
    IrreversibleWriteGuardService,
)


@pytest.fixture
def service() -> IrreversibleWriteGuardService:
    """Create a fresh IrreversibleWriteGuardService instance."""
    return IrreversibleWriteGuardService()


def test_service_intercept_safe_tool(service: IrreversibleWriteGuardService) -> None:
    """Verify safe tools bypass pre-flight interception."""
    req = InterceptToolCallRequest(
        session_id="sess_safe",
        tool_name="read_file",
        arguments={"path": "/workspace/main.py"},
    )
    res = service.intercept_tool_call(req)
    assert res.intercepted is False
    assert res.intent is None
    assert "not registered" in res.reason


def test_service_intercept_irreversible_tool(service: IrreversibleWriteGuardService) -> None:
    """Verify irreversible tools are intercepted and produce a blast radius card."""
    req = InterceptToolCallRequest(
        session_id="sess_write",
        tool_name="send_email",
        arguments={"to": "client@example.com", "subject": "Contract Draft", "body": "See attached"},
    )
    res = service.intercept_tool_call(req)
    assert res.intercepted is True
    assert res.intent is not None
    assert res.intent.status == "pending_confirmation"
    assert res.intent.blast_radius.domain == "email"
    assert res.intent.blast_radius.details["to"] == "client@example.com"


def test_service_approve_intent(service: IrreversibleWriteGuardService) -> None:
    """Verify approving an intercepted intent transitions status to approved."""
    req = InterceptToolCallRequest(
        session_id="sess_appr",
        tool_name="git_push",
        arguments={"remote": "origin", "branch": "feature/ui"},
    )
    res = service.intercept_tool_call(req)
    assert res.intent is not None
    intent_id = res.intent.intent_id

    # Pending list should have 1 item
    pending = service.list_pending("sess_appr")
    assert len(pending) == 1

    # Approve
    approved = service.approve_intent(
        intent_id=intent_id,
        req=ApproveIntentRequest(approver="developer_bob"),
    )
    assert approved.status == "approved"
    assert "developer_bob" in approved.resolution_reason

    # Pending list should now be empty
    assert len(service.list_pending("sess_appr")) == 0


def test_service_emergency_kill(service: IrreversibleWriteGuardService) -> None:
    """Verify emergency kill switch destroys pending action payload."""
    req = InterceptToolCallRequest(
        session_id="sess_kill",
        tool_name="stripe_charge",
        arguments={"amount": "1200", "currency": "USD", "recipient": "unverified_vendor"},
    )
    res = service.intercept_tool_call(req)
    assert res.intent is not None
    intent_id = res.intent.intent_id

    kill_res = service.emergency_kill(
        intent_id=intent_id,
        req=EmergencyKillRequest(reason="Suspicious transaction identified"),
    )
    assert kill_res.killed is True
    assert "Suspicious transaction" in kill_res.reason

    # Retrieved intent reflects aborted status
    stored = service.get_intent(intent_id)
    assert stored is not None
    assert stored.status == "killed_aborted"
    assert stored.arguments == {}


def test_service_contract_management(service: IrreversibleWriteGuardService) -> None:
    """Verify registering and listing contracts."""
    reg_req = RegisterContractRequest(
        tool_name="slack_post_public",
        domain="im_broadcast",
        description="Post message to public company Slack channel",
        default_risk_level="medium",
    )
    contract_res = service.register_contract(reg_req)
    assert contract_res.tool_name == "slack_post_public"
    assert contract_res.domain == "im_broadcast"

    contracts = service.list_contracts()
    tool_names = [c.tool_name for c in contracts]
    assert "slack_post_public" in tool_names
    assert "git_push" in tool_names
