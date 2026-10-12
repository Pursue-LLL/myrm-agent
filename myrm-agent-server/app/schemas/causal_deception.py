"""Pydantic schemas for Causal Deception Defense & Mechanism Probe.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for upfront commitments, execution traces, post-report claims,
  three-way invariance audit reports, and counterfactual audience probes.

[POS]
- Server schemas. Exposes typed contracts for client UI and security audit endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = str | int | float | bool | None


class CommitmentItemDto(BaseModel):
    """Upfront plan or action commitment made by the agent."""

    model_config = ConfigDict(extra="forbid")

    commitment_id: str = Field(..., description="Unique commitment identifier")
    commitment_type: str = Field(
        ..., description="Type of commitment, e.g. TEST_RUN, CODE_MODIFICATION, FILE_READ"
    )
    target_subject: str = Field(..., description="Target file, module, or test subject")
    description: str = Field(..., description="Commitment statement or intent summary")


class ExecutionTraceItemDto(BaseModel):
    """Objective physical execution record from runtime tool logs."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(..., description="Unique trace identifier")
    tool_name: str = Field(..., description="Name of the invoked tool")
    arguments: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Tool invocation arguments"
    )
    output_summary: str = Field(default="", description="Summary of tool execution output")
    is_success: bool = Field(default=True, description="Whether tool execution succeeded")
    timestamp: str = Field(default="", description="ISO timestamp of execution")


class PostReportClaimDto(BaseModel):
    """Factual claim stated in the post-execution report."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(..., description="Unique claim identifier")
    commitment_type: str = Field(
        ..., description="Category matching commitment type"
    )
    claimed_status: str = Field(
        ..., description="Asserted outcome, e.g. PASSED, MODIFIED, VERIFIED"
    )
    target_subject: str = Field(..., description="Target file or component claimed")
    assertion_text: str = Field(..., description="Exact textual claim from post-report")


class InvarianceViolationDto(BaseModel):
    """Detected discrepancy between post-report claims and physical execution traces."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(..., description="Associated claim ID")
    verdict: str = Field(..., description="Violation verdict, e.g. DECEPTIVE_FABRICATION")
    reason: str = Field(..., description="Explanation of why claim violates invariance")
    target_subject: str = Field(..., description="Target subject of the violation")


class AuditCausalConsistencyRequest(BaseModel):
    """Payload to evaluate commitment-execution-report invariance."""

    model_config = ConfigDict(extra="forbid")

    commitments: list[CommitmentItemDto] = Field(
        default_factory=list, description="List of upfront commitments"
    )
    traces: list[ExecutionTraceItemDto] = Field(
        default_factory=list, description="List of physical tool execution traces"
    )
    claims: list[PostReportClaimDto] = Field(
        ..., description="List of claims extracted from post-execution report"
    )
    fail_closed: bool = Field(
        default=False, description="Whether to raise HTTP 422 if deception is detected"
    )


class AuditCausalConsistencyResponse(BaseModel):
    """Audit verdict evaluating three-way causal consistency."""

    model_config = ConfigDict(extra="forbid")

    is_consistent: bool = Field(..., description="Whether claims are fully grounded in traces")
    overall_verdict: str = Field(..., description="MATCH, UNVERIFIED_CLAIM, or DECEPTIVE_FABRICATION")
    total_commitments: int = Field(..., description="Total commitments evaluated")
    total_traces: int = Field(..., description="Total execution traces evaluated")
    total_claims: int = Field(..., description="Total claims evaluated")
    risk_score: float = Field(..., description="Deception risk score from 0.0 to 1.0")
    violations: list[InvarianceViolationDto] = Field(
        default_factory=list, description="Detected invariance violations"
    )


class AudienceProbeRequest(BaseModel):
    """Payload to probe whether report deceptively sugarcoats facts for novice recipients."""

    model_config = ConfigDict(extra="forbid")

    claims: list[PostReportClaimDto] = Field(..., description="Report claims to evaluate")
    traces: list[ExecutionTraceItemDto] = Field(
        default_factory=list, description="Physical execution traces"
    )
    audience_level: str = Field(
        default="NOVICE", description="Target recipient technical tier (NOVICE, INTERMEDIATE, SENIOR_ENGINEER)"
    )


class AudienceProbeResponse(BaseModel):
    """Result of counterfactual audience vulnerability probe."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str = Field(..., description="Unique probe identifier")
    baseline_audience: str = Field(..., description="Evaluated baseline audience level")
    adversarial_audience: str = Field(..., description="Counterfactual senior engineer audience level")
    is_asymmetric_deception: bool = Field(
        ..., description="Whether report exploits recipient technical blindspots"
    )
    discrepancy_details: str = Field(..., description="Detailed explanation of detected discrepancy")
    vulnerability_index: float = Field(..., description="Vulnerability score from 0.0 to 1.0")
