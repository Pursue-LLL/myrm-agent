"""
[POS] app/schemas/policy_conformance.py
[INPUT] pydantic
[OUTPUT] Agent policy conformance & message routing DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyBaselineDTO(BaseModel):
    """Enterprise policy baseline declaring permitted models, tools, and security gates."""

    baseline_id: str = Field(..., description="Unique baseline identifier")
    allowed_model_providers: list[str] = Field(
        default_factory=lambda: ["openai", "anthropic", "deepseek"],
        description="Permitted LLM vendor providers",
    )
    allowed_mcp_servers: list[str] = Field(
        default_factory=lambda: ["memory", "calculator", "browser"],
        description="Whitelisted MCP servers",
    )
    prohibited_domains: list[str] = Field(
        default_factory=lambda: ["*.onion", "darknet.internal", "phishing-test.org"],
        description="Forbidden network destinations",
    )
    max_temperature: float = Field(default=1.0, description="Upper bound for LLM temperature")
    enforce_approval_gate: bool = Field(default=True, description="Whether approval gate is mandated")


class AgentRuntimeConfigDTO(BaseModel):
    """Observed runtime configuration snapshot of an agent."""

    agent_id: str = Field(..., description="Unique agent identifier")
    model_provider: str = Field(..., description="Configured LLM provider")
    loaded_mcp_servers: list[str] = Field(default_factory=list, description="Currently loaded MCP servers")
    configured_egress_domains: list[str] = Field(
        default_factory=list, description="Target network destinations"
    )
    temperature: float = Field(default=0.7, description="Sampling temperature")
    approval_gate_enabled: bool = Field(default=True, description="Whether approval gate is enabled")


class ConfigDriftFindingDTO(BaseModel):
    """Individual non-conformance finding identified during baseline audit."""

    agent_id: str = Field(..., description="Agent with detected drift")
    field_name: str = Field(..., description="Configuration field that drifted")
    severity: str = Field(..., description="Drift severity level")
    expected_value: str = Field(..., description="Baseline expectation")
    actual_value: str = Field(..., description="Actual agent setting")
    remediation_advice: str = Field(..., description="Actionable fix recommendation")


class RoutingRuleDTO(BaseModel):
    """Semantic mapping rule routing conversations to specialized agents."""

    agent_id: str = Field(..., description="Target specialized agent ID")
    keywords: list[str] = Field(default_factory=list, description="Matching keywords")
    intent_tags: list[str] = Field(default_factory=list, description="Matching intent tags")


class RoutingTestCaseDTO(BaseModel):
    """Synthetic conversation query used for zero-cost message-routing assertion."""

    case_id: str = Field(..., description="Unique test case identifier")
    sample_message: str = Field(..., description="Simulated incoming prompt")
    expected_agent_id: str = Field(..., description="Target agent that should handle query")
    required_keywords: list[str] = Field(default_factory=list, description="Mandatory query keywords")


class RoutingVerificationResultDTO(BaseModel):
    """Outcome of verifying a synthetic incoming query against routing rules."""

    case_id: str = Field(..., description="Test case identifier")
    is_matched: bool = Field(..., description="Whether routed agent matches expected agent")
    expected_agent_id: str = Field(..., description="Expected destination")
    routed_agent_id: str = Field(..., description="Evaluated destination")
    confidence_score: float = Field(..., description="Confidence score between 0.0 and 1.0")
    diagnostic: str = Field(..., description="Assertion diagnostic details")


class AuditAgentsRequestDTO(BaseModel):
    """Request payload to audit agent runtime configs against current baseline."""

    agents: list[AgentRuntimeConfigDTO] = Field(..., description="List of agent configs to audit")


class AuditAgentsResponseDTO(BaseModel):
    """Audit outcome for collection of agents."""

    conformance_score: int = Field(..., description="Computed health score (0-100)")
    findings: list[ConfigDriftFindingDTO] = Field(..., description="Identified drift findings")


class RemediateAgentRequestDTO(BaseModel):
    """Request payload to remediate an agent config according to current baseline."""

    config: AgentRuntimeConfigDTO = Field(..., description="Agent config requiring remediation")


class RemediateAgentResponseDTO(BaseModel):
    """Remediated configuration aligned with baseline."""

    remediated_config: AgentRuntimeConfigDTO = Field(..., description="Cleaned compliant configuration")


class VerifyRoutingRequestDTO(BaseModel):
    """Request payload for zero-cost synthetic message routing verification."""

    rules: list[RoutingRuleDTO] = Field(default_factory=list, description="Routing rules to apply")
    test_cases: list[RoutingTestCaseDTO] = Field(..., description="Synthetic test cases to assert")


class VerifyRoutingResponseDTO(BaseModel):
    """Result of synthetic message routing verification."""

    pass_rate: float = Field(..., description="Percentage pass rate across cases")
    results: list[RoutingVerificationResultDTO] = Field(..., description="Individual case results")


class FullConformanceAuditRequestDTO(BaseModel):
    """Comprehensive audit request including agent configs and synthetic routing tests."""

    agents: list[AgentRuntimeConfigDTO] = Field(..., description="Agent runtime configurations")
    rules: list[RoutingRuleDTO] = Field(default_factory=list, description="Semantic routing rules")
    test_cases: list[RoutingTestCaseDTO] = Field(
        default_factory=list, description="Synthetic message routing cases"
    )


class FullConformanceAuditResponseDTO(BaseModel):
    """Comprehensive policy audit report."""

    audit_id: str = Field(..., description="Unique audit run identifier")
    conformance_score: int = Field(..., description="Computed health score (0-100)")
    total_agents_checked: int = Field(..., description="Number of agents evaluated")
    drift_findings: list[ConfigDriftFindingDTO] = Field(..., description="Drift findings")
    routing_pass_rate: float = Field(..., description="Routing assertion accuracy")
    routing_results: list[RoutingVerificationResultDTO] = Field(..., description="Routing assertions")
    summary_badge: str = Field(..., description="Summary status badge")


class PolicyAuditorMetricsDTO(BaseModel):
    """Operational telemetry metrics for policy audits."""

    audits_executed_total: int = Field(..., description="Total audit executions")
    agents_audited_total: int = Field(..., description="Total agents evaluated")
    drifts_detected_total: int = Field(..., description="Total drift findings caught")
    routing_checks_run_total: int = Field(..., description="Total routing cases tested")
    routing_checks_passed_total: int = Field(..., description="Total routing cases passed")
