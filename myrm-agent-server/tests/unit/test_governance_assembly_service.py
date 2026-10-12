"""Unit tests for GovernanceAssemblyService."""

from __future__ import annotations

from app.schemas.governance_assembly import (
    RecordInvocationRequest,
    SimulateWorkflowRequest,
    VerifyToolGovernanceRequest,
)
from app.services.security.governance_assembly_service import GovernanceAssemblyService


def test_governance_assembly_service_record_and_report() -> None:
    service = GovernanceAssemblyService()
    service.reset()

    # Record governed call
    dto = service.record_invocation(
        RecordInvocationRequest(
            tool_name="search_database",
            ingress_source="INTERACTIVE_CHAT",
            applied_middlewares=["EStopCheck", "LoopGuard", "ToolInterceptorMiddleware", "TripartiteLedgerGate"],
            is_governed=True,
        )
    )
    assert dto.tool_name == "search_database"
    assert dto.is_governed is True

    # Check matrix report
    report = service.get_matrix_report()
    assert report.total_invocations == 1
    assert report.governed_invocations == 1
    assert report.is_fully_compliant is True


def test_verify_tool_governance() -> None:
    service = GovernanceAssemblyService()

    # Valid tool
    resp_valid = service.verify_tool_governance(
        VerifyToolGovernanceRequest(
            tool_name="read_file",
            applied_middlewares=["EStopCheck", "LoopGuard", "ToolInterceptorMiddleware", "TripartiteLedgerGate"],
        )
    )
    assert resp_valid.is_valid is True
    assert len(resp_valid.missing_middlewares) == 0

    # Incomplete tool
    resp_invalid = service.verify_tool_governance(
        VerifyToolGovernanceRequest(
            tool_name="shell_exec",
            applied_middlewares=["EStopCheck"],
        )
    )
    assert resp_invalid.is_valid is False
    assert "ToolInterceptorMiddleware" in resp_invalid.missing_middlewares


def test_simulate_workflow_governed_and_naked() -> None:
    service = GovernanceAssemblyService()
    service.reset()

    # 1. Governed workflow
    res_gov = service.simulate_workflow(
        SimulateWorkflowRequest(
            scenario_name="web_chat",
            ingress_source="INTERACTIVE_CHAT",
            tools=["tool_a", "tool_b"],
            simulate_naked_tool=False,
        )
    )
    assert res_gov.is_governed is True
    assert len(res_gov.results) == 2

    # 2. Naked tool workflow intercepted by watchdog
    res_naked = service.simulate_workflow(
        SimulateWorkflowRequest(
            scenario_name="cron_leak",
            ingress_source="BACKGROUND_CRON",
            tools=["tool_safe", "tool_naked"],
            simulate_naked_tool=True,
        )
    )
    assert res_naked.is_governed is False
    assert any("[BLOCKED_BY_WATCHDOG]" in r for r in res_naked.results)
