"""Pydantic schemas for Independent Risk Evaluator Agent and OS Security Scanner.

[INPUT]
None.

[OUTPUT]
DTO models for proposal evaluation, OS-level runtime command scanning, and audit ledger tracking.

[POS]
Server schemas. Exposes typed contracts for independent risk assessment and ECC-style OS guard.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class ActionProposalDto(BaseModel):
    """Proposal specification submitted for independent risk evaluation."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., description="Unique proposal identifier")
    action_type: str = Field(..., description="Action classification: financial_transaction, system_operation, etc.")
    title: str = Field(..., description="Action title or summary")
    description: str = Field(..., description="Detailed explanation of the proposed action")
    estimated_cost: float = Field(default=0.0, description="Estimated economic or compute cost")
    blast_radius_scope: str = Field(default="local", description="Scope: local, cluster, external, global")
    rollback_supported: bool = True
    raw_command_or_payload: str | None = Field(default=None, description="Optional raw shell command or code")
    target_resources: list[str] = Field(default_factory=list, description="Target files or system assets")


class OsOperatorScanResultDto(BaseModel):
    """Vulnerability scan verdict for an OS-level shell command."""

    model_config = ConfigDict(extra="forbid")

    safe: bool = Field(..., description="True if command exhibits no threat signatures")
    command_signature: str = Field(..., description="Normalized command executable token")
    detected_vulnerabilities: list[str] = Field(default_factory=list, description="List of detected threats")
    blocked_patterns: list[str] = Field(default_factory=list, description="Regex patterns that matched")
    scanned_at: float = Field(default_factory=time.time, description="Scan timestamp")


class RiskEvaluationReportDto(BaseModel):
    """Independent Risk Evaluator verdict report."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(..., description="Unique evaluation report identifier")
    proposal_id: str = Field(..., description="Associated proposal ID")
    tier: str = Field(..., description="Risk tier: pass_safe, warn_elevated, block_critical")
    risk_score: float = Field(..., description="Aggregated risk score (0.0 - 100.0)")
    approved: bool = Field(..., description="True if proposal is authorized to proceed")
    blast_radius_score: float = Field(..., description="Risk score component for blast radius")
    rollback_feasible: bool = Field(..., description="Whether action is reversible")
    violations: list[str] = Field(default_factory=list, description="List of identified violations")
    recommendations: list[str] = Field(default_factory=list, description="Recommended remediation actions")
    os_scan_result: OsOperatorScanResultDto | None = Field(default=None, description="OS-level command scan verdict")
    evaluated_at: float = Field(default_factory=time.time, description="Evaluation timestamp")


class EvaluateProposalRequest(BaseModel):
    """Payload to evaluate an action proposal through the independent risk agent."""

    model_config = ConfigDict(extra="forbid")

    proposal: ActionProposalDto = Field(..., description="Action proposal to assess")
    strict_mode: bool = Field(default=False, description="Whether to enforce lower risk thresholds")


class EvaluateProposalResponse(BaseModel):
    """Result of independent proposal risk assessment."""

    model_config = ConfigDict(extra="forbid")

    report: RiskEvaluationReportDto = Field(..., description="Evaluation verdict report")
    verdict: str = Field(..., description="Human-readable decision: APPROVED, ELEVATED_WARNING, or BLOCKED")


class OsCommandScanRequest(BaseModel):
    """Payload to scan a shell command before terminal execution."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="Raw shell command string to scan")


class OsCommandScanResponse(BaseModel):
    """Scan response indicating if command is safe to execute."""

    model_config = ConfigDict(extra="forbid")

    scan_result: OsOperatorScanResultDto = Field(..., description="Detailed AST and pattern scan result")


class RiskAuditEntryDto(BaseModel):
    """Structured record in the risk audit ledger."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Audit entry identifier")
    proposal_id: str = Field(..., description="Proposal ID")
    title: str = Field(..., description="Action title")
    tier: str = Field(..., description="Assessed risk tier")
    risk_score: float = Field(..., description="Aggregated risk score")
    outcome: str = Field(..., description="Lifecycle outcome: approved, rejected, executed, aborted")
    recorded_at: float = Field(..., description="Unix epoch timestamp")


class RiskAuditLedgerResponse(BaseModel):
    """Response containing queried risk audit ledger records."""

    model_config = ConfigDict(extra="forbid")

    entries: list[RiskAuditEntryDto] = Field(default_factory=list, description="Audit entries")
    count: int = Field(..., description="Total records returned")
