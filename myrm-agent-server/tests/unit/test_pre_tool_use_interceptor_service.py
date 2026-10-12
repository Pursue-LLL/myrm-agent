"""Unit tests for PreToolUseInterceptorService in myrm-agent-server."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.pre_tool_use_interceptor import (
    HardGateSecurityRejectionError,
    PreToolUseHookInterceptor,
)

from app.schemas.pre_tool_use_interceptor import (
    DetectApiKeyConflictRequest,
    InterceptToolUseRequest,
)
from app.services.security.pre_tool_use_interceptor_service import (
    PreToolUseInterceptorService,
    get_pre_tool_use_interceptor_service,
)


@pytest.fixture
def service() -> PreToolUseInterceptorService:
    interceptor = PreToolUseHookInterceptor()
    return PreToolUseInterceptorService(interceptor=interceptor)


def test_service_intercept_allowed(
    service: PreToolUseInterceptorService,
) -> None:
    req = InterceptToolUseRequest(
        tool_name="run_command",
        payload_str="git push origin feature/user-profile",
    )
    resp = service.intercept_tool(req)
    assert resp.verdict == "ALLOW"
    assert resp.blocked_rule_id is None


def test_service_intercept_blocked(
    service: PreToolUseInterceptorService,
) -> None:
    req = InterceptToolUseRequest(
        tool_name="run_command",
        payload_str="git push origin main",
        raise_on_block=False,
    )
    resp = service.intercept_tool(req)
    assert resp.verdict == "BLOCK"
    assert resp.rule_category == "PROTECTED_BRANCH_PUSH"
    assert resp.blocked_rule_id == "RULE-PROT-BRANCH"
    assert resp.rejection_reason is not None


def test_service_intercept_raise_on_block(
    service: PreToolUseInterceptorService,
) -> None:
    req = InterceptToolUseRequest(
        tool_name="run_command",
        payload_str="DROP DATABASE prod_db;",
        raise_on_block=True,
    )
    with pytest.raises(HardGateSecurityRejectionError):
        service.intercept_tool(req)


def test_service_detect_key_conflicts(
    service: PreToolUseInterceptorService,
) -> None:
    req_conflict = DetectApiKeyConflictRequest(
        active_provider="anthropic",
        is_subscription_route=True,
        env_dict={"ANTHROPIC_API_KEY": "sk-ant-test-key"},
    )
    res_conflict = service.detect_key_conflicts(req_conflict)
    assert res_conflict.has_conflict is True
    assert "ANTHROPIC_API_KEY" in res_conflict.detected_env_vars
    assert res_conflict.warning_message is not None

    req_clean = DetectApiKeyConflictRequest(
        active_provider="anthropic",
        is_subscription_route=True,
        env_dict={},
    )
    res_clean = service.detect_key_conflicts(req_clean)
    assert res_clean.has_conflict is False


def test_service_toggle_rule(
    service: PreToolUseInterceptorService,
) -> None:
    # 1. Initially blocked
    req = InterceptToolUseRequest(
        tool_name="run_command",
        payload_str="git push origin main",
    )
    assert service.intercept_tool(req).verdict == "BLOCK"

    # 2. Disable rule
    toggled = service.toggle_rule("RULE-PROT-BRANCH", enabled=False)
    assert toggled is True
    assert service.intercept_tool(req).verdict == "ALLOW"

    # 3. Re-enable rule
    service.toggle_rule("RULE-PROT-BRANCH", enabled=True)
    assert service.intercept_tool(req).verdict == "BLOCK"


def test_service_singleton() -> None:
    svc1 = get_pre_tool_use_interceptor_service()
    svc2 = get_pre_tool_use_interceptor_service()
    assert svc1 is svc2
