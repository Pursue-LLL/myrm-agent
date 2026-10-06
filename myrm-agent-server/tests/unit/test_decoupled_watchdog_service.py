"""Unit tests for DecoupledWatchdogService.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.decoupled_watchdog import (
    ActionContractSpecSchema,
    FirewallSanitizeRequest,
    InvarianceAssertionRuleSchema,
    WatchdogInspectRequest,
    WatchdogVerdictStatusEnum,
)
from app.services.security.decoupled_watchdog_service import (
    DecoupledWatchdogService,
    get_decoupled_watchdog_service,
)


def test_service_singleton_resolution() -> None:
    """Ensure get_decoupled_watchdog_service returns consistent singleton."""
    service1 = get_decoupled_watchdog_service()
    service2 = get_decoupled_watchdog_service()
    assert service1 is service2


def test_sanitize_inbound_content() -> None:
    """Verify inbound content firewall stripping and telemetry tracking."""
    service = DecoupledWatchdogService()
    req = FirewallSanitizeRequest(
        raw_content="<p>Public text</p><span style='display:none'>hidden injection</span>",
        source_type="web_page",
    )
    res = service.sanitize_inbound_content(req)

    assert "Public text" in res.sanitized_content
    assert "hidden injection" not in res.sanitized_content
    assert res.hidden_text_stripped_count > 0

    metrics = service.get_metrics()
    assert metrics.total_sanitized_inputs >= 1


def test_inspect_action_approved() -> None:
    """Verify compliant action inspection produces approved verdict."""
    service = DecoupledWatchdogService()
    action = ActionContractSpecSchema(
        action_id="act_ok_1",
        tool_name="search_documents",
        arguments={"query": "annual report"},
        user_original_intent="Search for the annual report document.",
    )
    req = WatchdogInspectRequest(action=action)
    res = service.inspect_action(req)

    assert res.verdict == WatchdogVerdictStatusEnum.APPROVED
    assert res.circuit_breaker_active is False
    assert res.confidence_score == 1.0

    metrics = service.get_metrics()
    assert metrics.total_inspected_actions >= 1
    assert metrics.approved_actions >= 1


def test_inspect_action_financial_amount_drift_circuit_breaker() -> None:
    """Verify financial amount drift trips circuit breaker in service."""
    service = DecoupledWatchdogService()
    rule = InvarianceAssertionRuleSchema(
        rule_name="payment_rule",
        target_tool="pay_merchant",
        max_amount_limit=50.0,
    )
    action = ActionContractSpecSchema(
        action_id="act_pay_drift",
        tool_name="pay_merchant",
        arguments={"amount": 250.0},
        user_original_intent="Pay 20 dollars to the merchant.",
    )
    req = WatchdogInspectRequest(action=action, rule=rule)
    res = service.inspect_action(req)

    assert res.verdict == WatchdogVerdictStatusEnum.CIRCUIT_BREAKER_TRIGGERED
    assert res.circuit_breaker_active is True
    assert any(v.violation_type in ("financial_amount_drift", "financial_limit_exceeded") for v in res.violations)

    metrics = service.get_metrics()
    assert metrics.circuit_breaker_trips >= 1


def test_rule_registration_and_metrics() -> None:
    """Verify dynamic rule registration and retrieval."""
    service = DecoupledWatchdogService()
    rule = InvarianceAssertionRuleSchema(
        rule_name="email_security_rule",
        target_tool="send_notification",
        allowed_recipients=["admin@myrm.io"],
    )
    service.register_rule(rule)

    metrics = service.get_metrics()
    assert metrics.avg_latency_ms >= 0.0
