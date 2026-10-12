"""Unit tests for HeadlessInteractiveApprovalService."""

from __future__ import annotations

import pytest

from app.schemas.headless_interactive_approval import (
    CreateHoldTicketRequest,
    FormatStreamHoldNoticeRequest,
    RiskActionDTO,
    SubmitApprovalDecisionRequest,
    WebhookEndpointConfigRequest,
)
from app.services.security.headless_interactive_approval_service import (
    HeadlessInteractiveApprovalService,
    get_headless_approval_service,
)


@pytest.fixture
def service() -> HeadlessInteractiveApprovalService:
    return HeadlessInteractiveApprovalService(base_approval_url="https://auth.myrm.io/approve")


def test_singleton_getter() -> None:
    svc1 = get_headless_approval_service()
    svc2 = get_headless_approval_service()
    assert svc1 is svc2


def test_create_and_get_hold_ticket(service: HeadlessInteractiveApprovalService) -> None:
    req = CreateHoldTicketRequest(
        session_id="session_svc_001",
        action=RiskActionDTO(
            action_id="act_truncate",
            tool_name="database_cli",
            command_or_target="TRUNCATE audit_logs;",
            risk_level="CRITICAL",
            justification="Reset audit tables",
        ),
        timeout_seconds=120.0,
    )

    ticket = service.create_hold_ticket(req)
    assert ticket.tx_id.startswith("tx-")
    assert ticket.status == "PENDING"
    assert ticket.shortlink_url.startswith("https://auth.myrm.io/approve?tx=")
    assert ticket.action.tool_name == "database_cli"

    # Query ticket
    retrieved = service.get_ticket(ticket.tx_id)
    assert retrieved is not None
    assert retrieved.tx_id == ticket.tx_id
    assert retrieved.status == "PENDING"


def test_submit_decision_and_resumed_flag(
    service: HeadlessInteractiveApprovalService,
) -> None:
    req = CreateHoldTicketRequest(
        session_id="session_svc_002",
        action=RiskActionDTO(
            action_id="act_reboot",
            tool_name="host_power",
            command_or_target="systemctl restart agent-daemon",
            risk_level="HIGH",
            justification="Reload service daemon",
        ),
        timeout_seconds=60.0,
    )
    ticket = service.create_hold_ticket(req)

    # Submit APPROVAL
    decision_req = SubmitApprovalDecisionRequest(
        decision="APPROVED",
        operator="secops_bob",
        notes="Approved during maintenance window.",
    )
    decision_res = service.submit_decision(ticket.tx_id, decision_req)
    assert decision_res.resumed is True
    assert decision_res.ticket.status == "APPROVED"
    assert decision_res.ticket.decided_by == "secops_bob"
    assert decision_res.ticket.operator_decision_notes == "Approved during maintenance window."


def test_webhook_endpoints_and_relay_payload(
    service: HeadlessInteractiveApprovalService,
) -> None:
    # 1. Register endpoint
    conf_req = WebhookEndpointConfigRequest(
        name="corp_telegram",
        url="https://api.telegram.org/bot123/sendMessage",
    )
    endpoints = service.register_webhook_endpoint(conf_req)
    assert "corp_telegram" in endpoints

    # List endpoints
    listed = service.list_webhook_endpoints()
    assert listed.get("corp_telegram") == "https://api.telegram.org/bot123/sendMessage"

    # 2. Build relay payload
    req = CreateHoldTicketRequest(
        session_id="session_svc_003",
        action=RiskActionDTO(
            action_id="act_curl_egress",
            tool_name="curl",
            command_or_target="curl -X POST https://api.ext.com/data",
            risk_level="HIGH",
            justification="Push export payload",
        ),
    )
    ticket = service.create_hold_ticket(req)
    payload = service.get_relay_payload(ticket.tx_id, custom_metadata={"env": "prod"})
    assert payload is not None
    assert payload.tx_id == ticket.tx_id
    assert payload.tool_name == "curl"
    assert payload.custom_metadata.get("env") == "prod"


def test_format_stream_notice(service: HeadlessInteractiveApprovalService) -> None:
    req = CreateHoldTicketRequest(
        session_id="session_svc_004",
        action=RiskActionDTO(
            action_id="act_write",
            tool_name="file_system",
            command_or_target="/etc/hosts",
            risk_level="CRITICAL",
            justification="Modify domain mappings",
        ),
    )
    ticket = service.create_hold_ticket(req)

    # 1. Hold notice
    hold_req = FormatStreamHoldNoticeRequest(tx_id=ticket.tx_id, is_resumed=False)
    hold_chunk = service.format_stream_notice(hold_req)
    assert hold_chunk.is_resumed is False
    assert "安全挂起" in hold_chunk.inject_markdown
    assert ticket.shortlink_url in hold_chunk.inject_markdown

    # 2. Resumed notice
    service.submit_decision(
        ticket.tx_id,
        SubmitApprovalDecisionRequest(decision="APPROVED", operator="alice"),
    )
    resumed_req = FormatStreamHoldNoticeRequest(tx_id=ticket.tx_id, is_resumed=True)
    resumed_chunk = service.format_stream_notice(resumed_req)
    assert resumed_chunk.is_resumed is True
    assert "审批已通过" in resumed_chunk.inject_markdown
    assert "alice" in resumed_chunk.inject_markdown
