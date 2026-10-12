"""Pydantic schemas for Governance Assembly Path Assertion & Zero-Bypass Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for multi-ingress governance matrices, tool wrapping signatures,
  and offline simulated workflow runs.

[POS]
- Server schemas. Exposes typed contracts for client UI and CI gate validation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GovernanceWrapperSignatureDto(BaseModel):
    """Signature proving a tool is wrapped by required governance middlewares."""

    model_config = ConfigDict(extra="forbid")

    wrapper_id: str = Field(..., description="Unique wrapper instance identifier")
    tool_name: str = Field(..., description="Target tool name")
    ingress_source: str = Field(..., description="Ingress channel (e.g. INTERACTIVE_CHAT, BACKGROUND_CRON)")
    applied_middlewares: list[str] = Field(..., description="Ordered list of applied middleware names")
    is_sealed: bool = Field(default=True, description="Whether the wrapper seal is intact")


class ToolCallAssemblyTraceDto(BaseModel):
    """Trace entry recording a tool call's path and governance status."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(..., description="Unique trace identifier")
    tool_name: str = Field(..., description="Name of executed tool")
    ingress_source: str = Field(..., description="Invocation ingress source")
    call_stack_summary: str = Field(..., description="Callstack summary representation")
    applied_middlewares: list[str] = Field(..., description="Observed middlewares on path")
    is_governed: bool = Field(..., description="Whether invocation was fully governed")
    bypassed_guards: list[str] = Field(default_factory=list, description="Guards that were bypassed")


class GovernanceMatrixReportDto(BaseModel):
    """Multi-ingress governance assembly coverage audit report."""

    model_config = ConfigDict(extra="forbid")

    total_invocations: int = Field(..., description="Total tool invocations observed")
    governed_invocations: int = Field(..., description="Invocations with verified governance wrappers")
    bypassed_invocations: int = Field(..., description="Invocations bypassing governance")
    coverage_ratio: float = Field(..., description="Ratio of governed over total invocations")
    is_fully_compliant: bool = Field(..., description="True if 100% path coverage and 0 bypasses")
    traces_by_ingress: dict[str, int] = Field(..., description="Invocation counts grouped by ingress source")
    violations: list[str] = Field(default_factory=list, description="Specific path violation details")


class RecordInvocationRequest(BaseModel):
    """Record an observed tool call on the execution path."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Tool name")
    ingress_source: str = Field(..., description="Ingress source (INTERACTIVE_CHAT, REST_API, etc.)")
    applied_middlewares: list[str] = Field(default_factory=list, description="Applied middleware names")
    is_governed: bool = Field(default=True, description="Whether tool passed governance wrapper")
    bypassed_guards: list[str] = Field(default_factory=list, description="Bypassed guard names")
    call_stack_summary: str = Field(default="", description="Optional call stack description")


class VerifyToolGovernanceRequest(BaseModel):
    """Request to verify if a tool configuration satisfies mandatory governance requirements."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Tool name to verify")
    applied_middlewares: list[str] = Field(..., description="Middlewares configured for this tool")


class VerifyToolGovernanceResponse(BaseModel):
    """Result of tool governance verification."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="True if tool satisfies all mandatory guards")
    tool_name: str = Field(..., description="Verified tool name")
    missing_middlewares: list[str] = Field(default_factory=list, description="Missing mandatory guards")
    message: str = Field(..., description="Status summary message")


class SimulateWorkflowRequest(BaseModel):
    """Run an offline recording-model workflow to assert assembly without LLM cost."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(..., description="Scenario: chat, cron, or subagent_dag")
    ingress_source: str = Field(default="INTERACTIVE_CHAT", description="Ingress channel to test")
    tools: list[str] = Field(default_factory=list, description="Tool names to register")
    simulate_naked_tool: bool = Field(
        default=False, description="If True, deliberately test naked tool rejection"
    )


class SimulateWorkflowResponse(BaseModel):
    """Outcome of offline recording workflow assembly assertion."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(..., description="Executed scenario name")
    ingress_source: str = Field(..., description="Ingress channel tested")
    executed_tools: list[str] = Field(..., description="Tools executed during workflow")
    is_governed: bool = Field(..., description="Whether workflow passed without bypasses")
    results: list[str] = Field(..., description="Tool output results")
    matrix_report: GovernanceMatrixReportDto = Field(..., description="Coverage report after workflow")
