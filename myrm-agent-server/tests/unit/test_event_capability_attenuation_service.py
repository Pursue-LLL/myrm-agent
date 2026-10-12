"""
[POS] tests/unit/test_event_capability_attenuation_service.py
[INPUT] app.services.security.event_capability_attenuation_service, app.schemas.event_capability_attenuation
[OUTPUT] Unit tests for EventCapabilityAttenuationService

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from myrm_agent_harness.core.security.event_capability_attenuation import (
    EventSignatureVerifier,
)

from app.schemas.event_capability_attenuation import (
    ApprovalTicketStatusEnum,
    ApproveTicketRequest,
    ChannelNotificationTargetSchema,
    ConsumeTokenRequest,
    CreateTicketRequest,
    EventIngestRequest,
    EventTrustScopeEnum,
    RegisterSecretRequest,
    RejectTicketRequest,
    SessionScopeUpdateRequest,
    TicketRiskLevelEnum,
    ToolEvaluationRequest,
)
from app.services.security.event_capability_attenuation_service import (
    EventCapabilityAttenuationService,
)


def test_service_secret_and_event_ingest() -> None:
    """Test registering source secrets and ingesting signed events."""
    service = EventCapabilityAttenuationService()
    source = "github_issues"
    secret = "issue_secret_key"
    payload = '{"action": "opened", "issue": {"title": "Fix memory leak"}}'

    # Register secret
    reg_ok = service.register_secret(RegisterSecretRequest(source_name=source, secret_key=secret))
    assert reg_ok is True

    # Compute valid signature
    verifier = EventSignatureVerifier()
    verifier.register_source_secret(source, secret)
    sig = verifier.compute_signature(source, payload.encode("utf-8"))

    # Ingest event with auto session binding
    session_id = "sess-event-101"
    res_valid = service.ingest_event(
        EventIngestRequest(
            event_id="evt-gh-01",
            source_name=source,
            event_type="issues",
            timestamp=time.time(),
            raw_payload_text=payload,
            signature=sig,
            auto_bind_session_id=session_id,
        )
    )
    assert res_valid.is_verified is True
    assert res_valid.bound_scope == EventTrustScopeEnum.LOW_TRUST_EVENT_SCOPE

    # Check session scope bound correctly
    scope_resp = service.get_session_scope(session_id)
    assert scope_resp.active_scope == EventTrustScopeEnum.LOW_TRUST_EVENT_SCOPE


def test_service_tool_evaluation_and_scope() -> None:
    """Test evaluating tool safety under interactive and attenuated scopes."""
    service = EventCapabilityAttenuationService()
    sess_id = "sess-eval-01"

    # Default is USER_INTERACTIVE
    eval_u = service.evaluate_tool(ToolEvaluationRequest(session_id=sess_id, tool_name="rm_rf"))
    assert eval_u.is_allowed is True
    assert eval_u.active_scope == EventTrustScopeEnum.USER_INTERACTIVE

    # Switch to LOW_TRUST_EVENT_SCOPE
    service.set_session_scope(
        sess_id, SessionScopeUpdateRequest(scope=EventTrustScopeEnum.LOW_TRUST_EVENT_SCOPE)
    )
    # Read tool allowed
    eval_r = service.evaluate_tool(ToolEvaluationRequest(session_id=sess_id, tool_name="file_read"))
    assert eval_r.is_allowed is True

    # Destructive tool blocked
    eval_b = service.evaluate_tool(ToolEvaluationRequest(session_id=sess_id, tool_name="shell_exec"))
    assert eval_b.is_allowed is False
    assert eval_b.risk_level in (TicketRiskLevelEnum.HIGH, TicketRiskLevelEnum.CRITICAL)


def test_service_ticket_workflow() -> None:
    """Test ticket creation, approval, token consumption, and rejection."""
    service = EventCapabilityAttenuationService()
    channel = ChannelNotificationTargetSchema(channel_type="telegram", target_id="@alerts_bot")

    # 1. Create ticket
    ticket = service.create_ticket(
        CreateTicketRequest(
            session_id="sess-tkt-01",
            requested_tool="git_push",
            risk_level=TicketRiskLevelEnum.HIGH,
            action_description="Auto-commit patch to main branch",
            diff_payload="diff --git a/file b/file",
            channels=[channel],
        )
    )
    assert ticket.status == ApprovalTicketStatusEnum.PENDING
    assert ticket.requested_tool == "git_push"

    # 2. List pending
    pending = service.list_pending_tickets()
    assert any(t.ticket_id == ticket.ticket_id for t in pending)

    # 3. Approve ticket
    app_res = service.approve_ticket(
        ticket.ticket_id,
        ApproveTicketRequest(decided_by="tech_lead", decision_reason="Verified by test"),
    )
    assert app_res is not None
    assert app_res.ticket.status == ApprovalTicketStatusEnum.APPROVED
    assert len(app_res.execution_token) > 0

    # 4. Consume token
    cons_res = service.consume_token(ConsumeTokenRequest(token=app_res.execution_token))
    assert cons_res.is_valid is True
    assert cons_res.matched_ticket_id == ticket.ticket_id

    # Secondary consume fails (one-time token)
    cons_re = service.consume_token(ConsumeTokenRequest(token=app_res.execution_token))
    assert cons_re.is_valid is False

    # 5. Reject another ticket
    t2 = service.create_ticket(
        CreateTicketRequest(
            session_id="sess-tkt-02",
            requested_tool="deploy_production",
            risk_level=TicketRiskLevelEnum.CRITICAL,
            action_description="Auto deploy on weekend",
            diff_payload="",
        )
    )
    rej_res = service.reject_ticket(
        t2.ticket_id,
        RejectTicketRequest(decided_by="secops", decision_reason="Freeze period"),
    )
    assert rej_res is not None
    assert rej_res.status == ApprovalTicketStatusEnum.REJECTED


def test_service_metrics() -> None:
    """Test operational telemetry metrics reporting."""
    service = EventCapabilityAttenuationService()
    metrics = service.get_metrics()
    assert metrics.total_events_received >= 0
    assert metrics.tickets_created >= 0
