"""Pydantic schemas for Kernel Continuous Enforcement, Formal Policy Prover,
Revocation Residue, and Supply Chain Suite.

[INPUT]
- pydantic BaseModel, ConfigDict, Field

[OUTPUT]
- NetworkPolicyRuleSchema: 3D network policy rule model
- RuntimeHopCheckRequestSchema: runtime egress evaluation request
- RuntimeHopCheckResponseSchema: runtime egress evaluation result
- PolicyProposalSubmitRequestSchema: proposal submission by agent
- ProverValidationResponseSchema: formal verification proof outcome
- ProposalDetailResponseSchema: proposal with status and prover analysis
- RevocationAuditRequestSchema: request executing revocation residue audit
- RevocationResidueReportResponseSchema: report detailing post-termination cleanliness

[POS]
Data contract for kernel continuous enforcement REST endpoints.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NetworkPolicyRuleSchema(BaseModel):
    """Schema for a 3D network policy rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique rule identifier")
    allowed_binaries: list[str] = Field(..., description="List of authorized binary names")
    endpoint_host: str = Field(..., description="Target hostname or IP pattern")
    endpoint_port: int = Field(..., ge=1, le=65535, description="Target port number")
    path_glob: str = Field(default="*", description="Path glob pattern")
    protocol: str = Field(default="rest", description="Protocol kind: rest, websocket, graphql, mcp, json-rpc, tcp")
    allow_upgrade_header: bool = Field(default=False, description="Whether Upgrade headers are permitted")
    provider_binding: str | None = Field(default=None, description="Bound credential provider identity")


class RuntimeHopCheckRequestSchema(BaseModel):
    """Schema for evaluating runtime egress hop against 3D policy."""

    model_config = ConfigDict(extra="forbid")

    binary_name: str = Field(..., description="Name of the executing binary (e.g., 'curl', 'python3')")
    host: str = Field(..., description="Target host being accessed")
    port: int = Field(..., ge=1, le=65535, description="Target port")
    path: str = Field(default="/", description="Target path")
    protocol: str = Field(default="rest", description="Protocol being used")
    has_upgrade_header: bool = Field(default=False, description="Whether request includes Upgrade header")


class RuntimeHopCheckResponseSchema(BaseModel):
    """Schema representing outcome of 3D continuous enforcement evaluation."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(..., description="Enforcement decision: 'allow' or 'deny'")
    rule_id: str | None = Field(None, description="Matched rule ID if allowed")
    reason: str = Field(..., description="Detailed attribution reason")
    violates_protocol_upgrade: bool = Field(default=False, description="Whether denied due to upgrade smuggling")


class PolicyProposalSubmitRequestSchema(BaseModel):
    """Schema for agent-proposed policy change submission."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., description="Unique proposal identifier")
    agent_id: str = Field(..., description="Agent proposing the rule relaxation")
    proposed_rules: list[NetworkPolicyRuleSchema] = Field(..., description="List of proposed rules")
    justification: str = Field(..., description="Natural language justification")


class ProverValidationResponseSchema(BaseModel):
    """Schema representing formal policy prover analysis."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., description="Evaluated proposal ID")
    is_safe: bool = Field(..., description="Whether formal verification proved safety invariants")
    risk_score: float = Field(..., description="Calculated normalized risk score (0.0 to 1.0)")
    flagged_risks: list[str] = Field(..., description="List of flagged invariant violations")
    formal_proof_summary: str = Field(..., description="Human-readable summary of formal proof")
    requires_human_approval: bool = Field(..., description="Whether human review is strictly required")


class ProposalDetailResponseSchema(BaseModel):
    """Schema representing full detail of a policy proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., description="Unique proposal ID")
    agent_id: str = Field(..., description="Agent ID")
    status: str = Field(..., description="Proposal status: PENDING, APPROVED, REJECTED")
    proposed_rules: list[NetworkPolicyRuleSchema] = Field(..., description="Rules in proposal")
    proof: ProverValidationResponseSchema = Field(..., description="Prover evaluation result")


class RevocationAuditRequestSchema(BaseModel):
    """Schema requesting a post-termination revocation residue audit."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Run or sandbox ID being audited")
    active_pids: list[int] = Field(default_factory=list, description="Surviving process IDs detected")
    open_sockets: list[str] = Field(default_factory=list, description="Surviving open sockets detected")
    temp_files: list[str] = Field(default_factory=list, description="Surviving temp or memory files detected")
    cached_tokens: list[str] = Field(default_factory=list, description="Surviving cached credential tokens")


class RevocationResidueReportResponseSchema(BaseModel):
    """Schema representing post-termination revocation residue audit report."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Audited run or sandbox ID")
    timestamp_iso: str = Field(..., description="Audit timestamp in ISO 8601 UTC")
    lingering_pids: list[int] = Field(..., description="Surviving process IDs")
    lingering_sockets: list[str] = Field(..., description="Surviving socket descriptors")
    lingering_tmp_files: list[str] = Field(..., description="Surviving temp files")
    lingering_cached_tokens: list[str] = Field(..., description="Surviving cached tokens")
    is_fully_clean: bool = Field(..., description="True if 0 surviving artifacts were found")
