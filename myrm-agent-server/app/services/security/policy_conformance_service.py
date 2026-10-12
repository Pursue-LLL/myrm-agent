"""
[POS] app/services/security/policy_conformance_service.py
[INPUT] app.schemas.policy_conformance, myrm_agent_harness.core.security.policy_conformance
[OUTPUT] PolicyConformanceService, get_policy_conformance_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.policy_conformance import (
    AgentPolicyConformanceFacade,
    AgentRuntimeConfig,
    PolicyBaseline,
    RoutingRule,
    RoutingTestCase,
)

from app.schemas.policy_conformance import (
    AgentRuntimeConfigDTO,
    AuditAgentsRequestDTO,
    AuditAgentsResponseDTO,
    ConfigDriftFindingDTO,
    FullConformanceAuditRequestDTO,
    FullConformanceAuditResponseDTO,
    PolicyAuditorMetricsDTO,
    PolicyBaselineDTO,
    RemediateAgentRequestDTO,
    RemediateAgentResponseDTO,
    RoutingRuleDTO,
    RoutingVerificationResultDTO,
    VerifyRoutingRequestDTO,
    VerifyRoutingResponseDTO,
)

logger = logging.getLogger(__name__)


class PolicyConformanceService:
    """Service orchestrating declarative enterprise policy audits and message routing verification."""

    def __init__(self, facade: AgentPolicyConformanceFacade | None = None) -> None:
        self._facade = facade or AgentPolicyConformanceFacade()

    def get_baseline(self) -> PolicyBaselineDTO:
        """Fetch active declarative policy baseline."""
        b = self._facade.get_baseline()
        return PolicyBaselineDTO(
            baseline_id=b.baseline_id,
            allowed_model_providers=list(b.allowed_model_providers),
            allowed_mcp_servers=list(b.allowed_mcp_servers),
            prohibited_domains=list(b.prohibited_domains),
            max_temperature=b.max_temperature,
            enforce_approval_gate=b.enforce_approval_gate,
        )

    def update_baseline(self, baseline_dto: PolicyBaselineDTO) -> PolicyBaselineDTO:
        """Update declarative enterprise policy baseline."""
        baseline = PolicyBaseline(
            baseline_id=baseline_dto.baseline_id,
            allowed_model_providers=tuple(baseline_dto.allowed_model_providers),
            allowed_mcp_servers=tuple(baseline_dto.allowed_mcp_servers),
            prohibited_domains=tuple(baseline_dto.prohibited_domains),
            max_temperature=baseline_dto.max_temperature,
            enforce_approval_gate=baseline_dto.enforce_approval_gate,
        )
        self._facade.update_baseline(baseline)
        return self.get_baseline()

    def register_routing_rule(self, rule_dto: RoutingRuleDTO) -> None:
        """Register or update semantic routing rule."""
        rule = RoutingRule(
            agent_id=rule_dto.agent_id,
            keywords=tuple(rule_dto.keywords),
            intent_tags=tuple(rule_dto.intent_tags),
        )
        self._facade.register_routing_rule(rule)

    def audit_agents(self, request: AuditAgentsRequestDTO) -> AuditAgentsResponseDTO:
        """Audit agent collection for configuration drifts against active baseline."""
        domain_agents = tuple(
            AgentRuntimeConfig(
                agent_id=a.agent_id,
                model_provider=a.model_provider,
                loaded_mcp_servers=tuple(a.loaded_mcp_servers),
                configured_egress_domains=tuple(a.configured_egress_domains),
                temperature=a.temperature,
                approval_gate_enabled=a.approval_gate_enabled,
            )
            for a in request.agents
        )
        findings = self._facade.audit_agents(domain_agents)
        score = 100 - sum(20 if f.severity == "CRITICAL_VIOLATION" else 5 for f in findings)
        score = max(0, score)

        findings_dtos = [
            ConfigDriftFindingDTO(
                agent_id=f.agent_id,
                field_name=f.field_name,
                severity=f.severity.value,
                expected_value=f.expected_value,
                actual_value=f.actual_value,
                remediation_advice=f.remediation_advice,
            )
            for f in findings
        ]
        return AuditAgentsResponseDTO(conformance_score=score, findings=findings_dtos)

    def remediate_agent(self, request: RemediateAgentRequestDTO) -> RemediateAgentResponseDTO:
        """Produce safe, baseline-aligned agent configuration snapshot."""
        c = request.config
        domain_config = AgentRuntimeConfig(
            agent_id=c.agent_id,
            model_provider=c.model_provider,
            loaded_mcp_servers=tuple(c.loaded_mcp_servers),
            configured_egress_domains=tuple(c.configured_egress_domains),
            temperature=c.temperature,
            approval_gate_enabled=c.approval_gate_enabled,
        )
        remediated = self._facade.remediate_agent(domain_config)
        return RemediateAgentResponseDTO(
            remediated_config=AgentRuntimeConfigDTO(
                agent_id=remediated.agent_id,
                model_provider=remediated.model_provider,
                loaded_mcp_servers=list(remediated.loaded_mcp_servers),
                configured_egress_domains=list(remediated.configured_egress_domains),
                temperature=remediated.temperature,
                approval_gate_enabled=remediated.approval_gate_enabled,
            )
        )

    def verify_routing(self, request: VerifyRoutingRequestDTO) -> VerifyRoutingResponseDTO:
        """Verify semantic message routing across synthetic test cases."""
        for rule_dto in request.rules:
            self.register_routing_rule(rule_dto)

        test_cases = tuple(
            RoutingTestCase(
                case_id=tc.case_id,
                sample_message=tc.sample_message,
                expected_agent_id=tc.expected_agent_id,
                required_keywords=tuple(tc.required_keywords),
            )
            for tc in request.test_cases
        )
        results = self._facade.verify_routing(test_cases)
        pass_rate = (
            (sum(1 for r in results if r.is_matched) / len(results) * 100.0) if results else 100.0
        )

        results_dtos = [
            RoutingVerificationResultDTO(
                case_id=r.case_id,
                is_matched=r.is_matched,
                expected_agent_id=r.expected_agent_id,
                routed_agent_id=r.routed_agent_id,
                confidence_score=r.confidence_score,
                diagnostic=r.diagnostic,
            )
            for r in results
        ]
        return VerifyRoutingResponseDTO(pass_rate=pass_rate, results=results_dtos)

    def run_full_audit(
        self, request: FullConformanceAuditRequestDTO
    ) -> FullConformanceAuditResponseDTO:
        """Execute full policy conformance and synthetic routing verification."""
        for rule_dto in request.rules:
            self.register_routing_rule(rule_dto)

        domain_agents = tuple(
            AgentRuntimeConfig(
                agent_id=a.agent_id,
                model_provider=a.model_provider,
                loaded_mcp_servers=tuple(a.loaded_mcp_servers),
                configured_egress_domains=tuple(a.configured_egress_domains),
                temperature=a.temperature,
                approval_gate_enabled=a.approval_gate_enabled,
            )
            for a in request.agents
        )
        test_cases = tuple(
            RoutingTestCase(
                case_id=tc.case_id,
                sample_message=tc.sample_message,
                expected_agent_id=tc.expected_agent_id,
                required_keywords=tuple(tc.required_keywords),
            )
            for tc in request.test_cases
        )
        report = self._facade.run_full_conformance_audit(
            agents=domain_agents, test_cases=test_cases
        )

        findings_dtos = [
            ConfigDriftFindingDTO(
                agent_id=f.agent_id,
                field_name=f.field_name,
                severity=f.severity.value,
                expected_value=f.expected_value,
                actual_value=f.actual_value,
                remediation_advice=f.remediation_advice,
            )
            for f in report.drift_findings
        ]
        results_dtos = [
            RoutingVerificationResultDTO(
                case_id=r.case_id,
                is_matched=r.is_matched,
                expected_agent_id=r.expected_agent_id,
                routed_agent_id=r.routed_agent_id,
                confidence_score=r.confidence_score,
                diagnostic=r.diagnostic,
            )
            for r in report.routing_results
        ]

        return FullConformanceAuditResponseDTO(
            audit_id=report.audit_id,
            conformance_score=report.conformance_score,
            total_agents_checked=report.total_agents_checked,
            drift_findings=findings_dtos,
            routing_pass_rate=report.routing_pass_rate,
            routing_results=results_dtos,
            summary_badge=report.summary_badge,
        )

    def get_metrics(self) -> PolicyAuditorMetricsDTO:
        """Fetch cumulative operational metrics."""
        m = self._facade.metrics
        return PolicyAuditorMetricsDTO(
            audits_executed_total=m.audits_executed_total,
            agents_audited_total=m.agents_audited_total,
            drifts_detected_total=m.drifts_detected_total,
            routing_checks_run_total=m.routing_checks_run_total,
            routing_checks_passed_total=m.routing_checks_passed_total,
        )


_global_service: PolicyConformanceService | None = None


def get_policy_conformance_service() -> PolicyConformanceService:
    """Singleton provider for PolicyConformanceService."""
    global _global_service
    if _global_service is None:
        _global_service = PolicyConformanceService()
    return _global_service
