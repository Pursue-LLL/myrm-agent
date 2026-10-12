"""
[POS] tests/unit/test_policy_conformance_service.py
Unit tests for PolicyConformanceService.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.policy_conformance import (
    AgentRuntimeConfigDTO,
    AuditAgentsRequestDTO,
    FullConformanceAuditRequestDTO,
    PolicyBaselineDTO,
    RemediateAgentRequestDTO,
    RoutingRuleDTO,
    RoutingTestCaseDTO,
    VerifyRoutingRequestDTO,
)
from app.services.security.policy_conformance_service import (
    PolicyConformanceService,
)


@pytest.fixture
def service() -> PolicyConformanceService:
    return PolicyConformanceService()


def test_baseline_management(service: PolicyConformanceService) -> None:
    initial = service.get_baseline()
    assert initial.baseline_id == "default-baseline-2026"
    assert "openai" in initial.allowed_model_providers

    updated_dto = PolicyBaselineDTO(
        baseline_id="custom-baseline-v2",
        allowed_model_providers=["anthropic", "deepseek"],
        allowed_mcp_servers=["memory", "calculator"],
        prohibited_domains=["*.onion", "darknet.internal"],
        max_temperature=0.8,
        enforce_approval_gate=True,
    )
    result = service.update_baseline(updated_dto)
    assert result.baseline_id == "custom-baseline-v2"
    assert "openai" not in result.allowed_model_providers
    assert "anthropic" in result.allowed_model_providers


def test_audit_agents_and_remediation(service: PolicyConformanceService) -> None:
    compliant = AgentRuntimeConfigDTO(
        agent_id="agent-01",
        model_provider="openai",
        loaded_mcp_servers=["memory"],
        configured_egress_domains=["safe.api.com"],
        temperature=0.5,
        approval_gate_enabled=True,
    )
    rogue = AgentRuntimeConfigDTO(
        agent_id="agent-02",
        model_provider="unauthorized_llm",
        loaded_mcp_servers=["memory", "unapproved_tool"],
        configured_egress_domains=["bad.darknet.internal"],
        temperature=1.5,
        approval_gate_enabled=False,
    )

    req = AuditAgentsRequestDTO(agents=[compliant, rogue])
    res = service.audit_agents(req)

    assert len(res.findings) >= 4
    assert res.conformance_score < 100

    # Test remediation
    rem_req = RemediateAgentRequestDTO(config=rogue)
    rem_res = service.remediate_agent(rem_req)
    remediated = rem_res.remediated_config

    assert remediated.model_provider == "openai"
    assert "unapproved_tool" not in remediated.loaded_mcp_servers
    assert "bad.darknet.internal" not in remediated.configured_egress_domains
    assert remediated.temperature <= 1.0
    assert remediated.approval_gate_enabled is True


def test_verify_routing(service: PolicyConformanceService) -> None:
    rules = [
        RoutingRuleDTO(
            agent_id="code_assistant",
            keywords=["code", "python", "bug"],
            intent_tags=["development"],
        ),
        RoutingRuleDTO(
            agent_id="finance_assistant",
            keywords=["stock", "revenue"],
            intent_tags=["finance"],
        ),
    ]
    test_cases = [
        RoutingTestCaseDTO(
            case_id="tc-1",
            sample_message="Fix this python bug in my code",
            expected_agent_id="code_assistant",
            required_keywords=["python"],
        ),
        RoutingTestCaseDTO(
            case_id="tc-2",
            sample_message="Analyze company quarterly revenue",
            expected_agent_id="finance_assistant",
            required_keywords=["revenue"],
        ),
    ]

    req = VerifyRoutingRequestDTO(rules=rules, test_cases=test_cases)
    res = service.verify_routing(req)

    assert res.pass_rate == 100.0
    assert len(res.results) == 2
    assert res.results[0].is_matched is True
    assert res.results[0].routed_agent_id == "code_assistant"
    assert res.results[1].is_matched is True
    assert res.results[1].routed_agent_id == "finance_assistant"


def test_full_conformance_audit_and_metrics(service: PolicyConformanceService) -> None:
    agent = AgentRuntimeConfigDTO(
        agent_id="agent-eval",
        model_provider="openai",
        loaded_mcp_servers=["memory"],
        configured_egress_domains=[],
        temperature=0.5,
        approval_gate_enabled=True,
    )
    rules = [
        RoutingRuleDTO(
            agent_id="agent-eval",
            keywords=["evaluate", "test"],
            intent_tags=["evaluation"],
        )
    ]
    test_cases = [
        RoutingTestCaseDTO(
            case_id="tc-eval-1",
            sample_message="Please evaluate this system test",
            expected_agent_id="agent-eval",
            required_keywords=["test"],
        )
    ]

    req = FullConformanceAuditRequestDTO(
        agents=[agent], rules=rules, test_cases=test_cases
    )
    res = service.run_full_audit(req)

    assert res.conformance_score == 100
    assert res.total_agents_checked == 1
    assert len(res.drift_findings) == 0
    assert res.routing_pass_rate == 100.0
    assert "🛡️ 策略合规评分: 100/100" in res.summary_badge

    metrics = service.get_metrics()
    assert metrics.audits_executed_total >= 1
    assert metrics.agents_audited_total >= 1
    assert metrics.routing_checks_run_total >= 1
    assert metrics.routing_checks_passed_total >= 1
