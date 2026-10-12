"""Pydantic DTO schemas for Dual-Track Soft Memory vs Hard Redline Sandbox Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for pre-execution physical sandbox firewall gating, rule registration,
  and compiled policy inspection.

[POS]
- Server schemas. Exposes typed contracts for physical sandbox firewall policy enforcement.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluateExecutionRequest(BaseModel):
    """Request payload to evaluate an operation against the sandbox physical execution firewall."""

    model_config = ConfigDict(extra="forbid")

    operation_type: str = Field(
        ..., description="Type of operation: 'file' or 'command'"
    )
    target: str = Field(
        ..., description="File path (if file) or full shell command string (if command)"
    )
    sub_operation: str = Field(
        default="read", description="Sub-operation for file access: 'read' or 'write'"
    )


class ExecutionInterceptionDto(BaseModel):
    """Outcome of sandbox execution firewall evaluation."""

    model_config = ConfigDict(extra="forbid")

    verdict: str = Field(
        ...,
        description="PERMITTED, BLOCKED_HARD_REDLINE_FILE, BLOCKED_HARD_REDLINE_COMMAND, "
        "or BLOCKED_EVASION_ATTEMPT",
    )
    is_permitted: bool = Field(
        ..., description="True if operation is permitted to proceed to OS/container execution"
    )
    blocked_by_rule_id: str | None = Field(
        default=None, description="Identifier of triggering hard redline rule if blocked"
    )
    target_operation: str = Field(
        ..., description="Target operation description or command line inspected"
    )
    audit_id: str = Field(
        ..., description="Unique immutable audit trace ID"
    )
    rationale: str = Field(
        ..., description="Interception rationale and firewall security trail"
    )


class RegisterRedlineRuleRequest(BaseModel):
    """Request payload to add a custom hard redline rule into the compiler."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique rule identifier (e.g. RL-FILE-099)")
    category: str = Field(
        ...,
        description="FILE_PROTECTION, COMMAND_PROTECTION, NETWORK_EGRESS, or PRIVILEGE_ESCALATION",
    )
    pattern: str = Field(..., description="Glob pattern for files or regex pattern for commands")
    description: str = Field(..., description="Human-readable safety constraint description")
    severity: str = Field(default="CRITICAL", description="Severity classification")


class HardRedlineRuleDto(BaseModel):
    """Hard redline rule definition specification."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique rule ID")
    category: str = Field(..., description="Redline category")
    pattern: str = Field(..., description="Rule pattern")
    description: str = Field(..., description="Description")
    severity: str = Field(..., description="Severity level")
    is_immutable: bool = Field(..., description="Immutable flag")


class CompiledPolicySummaryDto(BaseModel):
    """Summary of compiled physical firewall execution rules."""

    model_config = ConfigDict(extra="forbid")

    rule_count: int = Field(..., description="Total active rules compiled")
    blocked_file_patterns: list[str] = Field(
        ..., description="Active glob patterns triggering file interception"
    )
    blocked_command_regexes: list[str] = Field(
        ..., description="Active regex patterns triggering shell command interception"
    )
    enforced_at: float = Field(..., description="Timestamp of compilation and enforcement")
