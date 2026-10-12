"""Unit tests for StackedPolicyGovernanceService in server."""

from __future__ import annotations

from myrm_agent_harness.core.security.stacked_policy_governance import (
    DowngradeGateSpec,
    PolicyRule,
)

from app.services.security.stacked_policy_governance_service import (
    StackedPolicyGovernanceService,
    get_stacked_policy_governance_service,
)


def test_service_singleton_and_custom_instance() -> None:
    """Test singleton and custom service instantiation."""
    s1 = get_stacked_policy_governance_service()
    s2 = get_stacked_policy_governance_service()
    assert s1 is s2

    custom = StackedPolicyGovernanceService(
        downgrade_spec=DowngradeGateSpec(soft_limit_tokens=5000)
    )
    assert custom is not None


def test_service_server_baseline_and_session_short_circuit() -> None:
    """Test server baseline enforcement and session-tier short circuit."""
    service = StackedPolicyGovernanceService()

    # 1. Server baseline blocks rm -rf *
    res_rm = service.evaluate(
        phase="tool_call",
        target="rm -rf *",
        session_id="sess_123",
    )
    assert res_rm.decision == "deny"
    assert res_rm.matched_tier == "server"

    # 2. Inject session rule blocking safe tool 'read_file'
    service.add_session_rule(
        PolicyRule(
            tier="session",
            name="block_read_in_session",
            phase="tool_call",
            action="deny",
            target_pattern="read_file",
            reason="User session restricted reading files",
            session_id="sess_restricted",
        )
    )

    # In sess_restricted, read_file is DENIED at session level
    res_read_blocked = service.evaluate(
        phase="tool_call",
        target="read_file",
        session_id="sess_restricted",
    )
    assert res_read_blocked.decision == "deny"
    assert res_read_blocked.matched_tier == "session"

    # In other session, read_file is ALLOWED
    res_read_ok = service.evaluate(
        phase="tool_call",
        target="read_file",
        session_id="sess_normal",
    )
    assert res_read_ok.decision == "allow"


def test_service_downgrade_gate_lifecycle() -> None:
    """Test tracking usage and graceful model fallback in service layer."""
    custom_spec = DowngradeGateSpec(
        soft_limit_tokens=500,
        soft_limit_cost=0.5,
        hard_limit_cost=2.0,
        primary_model="claude-3-7-sonnet",
        fallback_model="gpt-4o-mini",
    )
    service = StackedPolicyGovernanceService(downgrade_spec=custom_spec)

    # Initial usage
    st1 = service.record_usage_and_check("sess_flow", 100, 0.05)
    assert st1.is_downgraded is False
    assert st1.active_model == "claude-3-7-sonnet"

    # Cross soft threshold
    st2 = service.record_usage_and_check("sess_flow", 450, 0.46)
    assert st2.is_downgraded is True
    assert st2.is_hard_blocked is False
    assert st2.active_model == "gpt-4o-mini"

    # Cross hard limit
    st3 = service.record_usage_and_check("sess_flow", 200, 1.6)
    assert st3.is_hard_blocked is True
    assert "Hard limit" in st3.message

    # Reset
    service.reset_session_budget("sess_flow")
    st_reset = service.get_downgrade_status("sess_flow")
    assert st_reset.is_downgraded is False
    assert st_reset.total_tokens == 0
