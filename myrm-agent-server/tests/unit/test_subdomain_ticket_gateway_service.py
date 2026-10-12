"""
Unit tests for Short-Lived Ticket Session Exchange & Subdomain Isolated Gateway Service.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.subdomain_ticket_gateway import (
    EvaluateAirgapRequest,
    IssueTicketRequest,
    RedeemTicketRequest,
    RevokeSessionRequest,
    ValidateSessionRequest,
)
from app.services.security.subdomain_ticket_gateway_service import (
    SubdomainTicketGatewayService,
)


def test_service_issue_and_redeem_ticket() -> None:
    service = SubdomainTicketGatewayService()

    # 1. Issue ticket
    issue_req = IssueTicketRequest(
        master_user_id="user-enterprise-01",
        target_instance_id="sandbox-inst-alpha",
        client_ip="172.16.0.4",
        client_fingerprint="fp-device-canvas-01",
    )
    issue_resp = service.issue_ticket(issue_req)
    assert issue_resp.ticket_id.startswith("tkt-")
    assert issue_resp.target_instance_id == "sandbox-inst-alpha"

    # 2. Redeem ticket
    redeem_req = RedeemTicketRequest(
        ticket_id=issue_resp.ticket_id,
        client_ip="172.16.0.4",
        client_fingerprint="fp-device-canvas-01",
    )
    redeem_resp = service.redeem_ticket(redeem_req)
    assert redeem_resp.status == "VALID"
    assert redeem_resp.session is not None
    assert redeem_resp.session.instance_id == "sandbox-inst-alpha"
    assert redeem_resp.session.user_id == "user-enterprise-01"

    # 3. Anti-replay prevention
    replay_resp = service.redeem_ticket(redeem_req)
    assert replay_resp.status == "ALREADY_CONSUMED"
    assert replay_resp.session is None


def test_service_client_fingerprint_mismatch() -> None:
    service = SubdomainTicketGatewayService()

    issue_resp = service.issue_ticket(
        IssueTicketRequest(
            master_user_id="user-enterprise-02",
            target_instance_id="sandbox-inst-beta",
            client_ip="172.16.0.5",
            client_fingerprint="fp-device-valid",
        )
    )

    # Spoofed fingerprint presentation
    spoofed_req = RedeemTicketRequest(
        ticket_id=issue_resp.ticket_id,
        client_ip="172.16.0.5",
        client_fingerprint="fp-device-spoofed",
    )
    redeem_resp = service.redeem_ticket(spoofed_req)
    assert redeem_resp.status == "FINGERPRINT_MISMATCH"
    assert redeem_resp.session is None


def test_service_validate_and_revoke_session() -> None:
    service = SubdomainTicketGatewayService()

    issue_resp = service.issue_ticket(
        IssueTicketRequest(
            master_user_id="user-enterprise-03",
            target_instance_id="sandbox-inst-gamma",
            client_ip="10.1.1.20",
            client_fingerprint="fp-device-03",
        )
    )
    redeem_resp = service.redeem_ticket(
        RedeemTicketRequest(
            ticket_id=issue_resp.ticket_id,
            client_ip="10.1.1.20",
            client_fingerprint="fp-device-03",
        )
    )
    assert redeem_resp.session is not None
    session_id = redeem_resp.session.session_id

    # Validate correct instance
    val_resp = service.validate_session(
        ValidateSessionRequest(
            session_id=session_id,
            instance_id="sandbox-inst-gamma",
        )
    )
    assert val_resp.is_valid

    # Validate incorrect instance
    val_wrong = service.validate_session(
        ValidateSessionRequest(
            session_id=session_id,
            instance_id="sandbox-inst-wrong",
        )
    )
    assert not val_wrong.is_valid

    # Revoke
    rev_resp = service.revoke_session(RevokeSessionRequest(session_id=session_id))
    assert rev_resp.success

    # Check after revocation
    val_after = service.validate_session(
        ValidateSessionRequest(
            session_id=session_id,
            instance_id="sandbox-inst-gamma",
        )
    )
    assert not val_after.is_valid


def test_service_evaluate_airgap_rules_and_metrics() -> None:
    service = SubdomainTicketGatewayService()

    # 1. Block master control plane call
    airgap_block = service.evaluate_airgap(
        EvaluateAirgapRequest(
            current_instance_id="inst-1",
            requested_path="/api/v1/admin/secrets/keys",
        )
    )
    assert not airgap_block.is_allowed
    assert airgap_block.verdict == "BLOCKED_MASTER_CONTROL_PLANE_ATTEMPT"

    # 2. Block cross-instance traversal
    cross_block = service.evaluate_airgap(
        EvaluateAirgapRequest(
            current_instance_id="inst-1",
            requested_path="/api/v1/tools/execute",
            target_instance_id="inst-2",
        )
    )
    assert not cross_block.is_allowed
    assert cross_block.verdict == "BLOCKED_CROSS_INSTANCE_ATTEMPT"

    # 3. Allow legitimate local call
    local_allow = service.evaluate_airgap(
        EvaluateAirgapRequest(
            current_instance_id="inst-1",
            requested_path="/api/v1/sandbox/eval",
            target_instance_id="inst-1",
        )
    )
    assert local_allow.is_allowed
    assert local_allow.verdict == "ALLOWED_SANDBOX_LOCAL"

    # 4. Metrics
    metrics = service.get_metrics()
    assert metrics.airgap_violations_blocked_total == 2
