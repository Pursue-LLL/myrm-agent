"""Pydantic schemas for Sandbox Log Redaction and Execution Continuation Audit.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for log redaction, run registration, heartbeats, and continuation audits.

[POS]
- Server schemas. Exposes typed contracts for sandbox log privacy and continuation reconciliation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RedactLogRequest(BaseModel):
    """Payload to redact credentials and tokens from sandbox logs and commands."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(..., description="Log text or stdout/stderr stream content")
    command: str | None = Field(
        default=None, description="Optional command line string to redact"
    )
    command_args: list[str] = Field(
        default_factory=list, description="Optional command argument list to redact"
    )


class RedactLogResponse(BaseModel):
    """Result of log and command redaction pass."""

    model_config = ConfigDict(extra="forbid")

    original_length: int = Field(..., description="Byte length of original raw text")
    redacted_text: str = Field(..., description="Sanitized text with masked secrets")
    redaction_count: int = Field(..., description="Total number of sensitive tokens replaced")
    categories_redacted: list[str] = Field(
        default_factory=list, description="List of detected secret categories"
    )
    redacted_command: str | None = Field(
        default=None, description="Redacted command string if requested"
    )
    redacted_command_args: list[str] = Field(
        default_factory=list, description="Redacted command argument list if requested"
    )


class RegisterRunRequest(BaseModel):
    """Payload to register an execution run under a task."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Unique execution run identifier")
    task_id: str = Field(..., description="Target task or workflow identifier")
    assignee_agent_id: str = Field(..., description="Identifier of the agent assigned to run")
    is_terminal: bool = Field(default=False, description="Whether the run is already terminal")


class RegisterRunResponse(BaseModel):
    """Registration confirmation of an execution run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Unique execution run identifier")
    task_id: str = Field(..., description="Target task identifier")
    assignee_agent_id: str = Field(..., description="Assigned agent identifier")
    is_terminal: bool = Field(..., description="Terminal state")
    started_at: float = Field(..., description="Run initialization timestamp")


class HeartbeatReportRequest(BaseModel):
    """Periodic heartbeat report from an active sandbox runner."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Active run identifier")
    timestamp: float = Field(..., description="Heartbeat generation timestamp")
    seq: int = Field(..., description="Monotonically increasing heartbeat sequence number")
    status: Literal["running", "idle", "busy", "terminating", "completed", "failed"] = Field(
        ..., description="Current execution runner status"
    )
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Runner health and telemetry metadata"
    )


class HeartbeatReportResponse(BaseModel):
    """Receipt acknowledging runner heartbeat processing."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="True if heartbeat was accepted for registered run")
    run_id: str = Field(..., description="Execution run identifier")
    seq: int = Field(..., description="Heartbeat sequence recorded")
    status: str = Field(..., description="Runner status recorded")


class ContinuationAuditRequest(BaseModel):
    """Request to verify whether an execution continuation is valid and authoritative."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task identifier")
    requesting_agent_id: str = Field(
        ..., description="Agent proposing to resume/execute continuation"
    )
    proposed_run_id: str = Field(..., description="Proposed new or continuing run ID")
    resume_source_run_id: str | None = Field(
        default=None, description="Prior run ID to resume from, if continuation"
    )
    max_heartbeat_gap_seconds: float = Field(
        default=60.0, description="Maximum permitted heartbeat inactivity duration"
    )


class ContinuationAuditResponse(BaseModel):
    """Verdict evaluating whether execution continuation is permitted."""

    model_config = ConfigDict(extra="forbid")

    is_resumable: bool = Field(..., description="True if continuation can proceed")
    status: str = Field(
        ...,
        description="VALID, STALE_HEARTBEAT, OWNERSHIP_MISMATCH, TASK_TERMINATED, or MISSING_ORIGIN_RUN",
    )
    task_id: str = Field(..., description="Task identifier")
    proposed_run_id: str = Field(..., description="Proposed run identifier")
    resume_source_run_id: str | None = Field(
        default=None, description="Prior run identifier if continuation"
    )
    reconciliation_reason: str = Field(
        ..., description="Audit rationale and reconciliation explanation"
    )
    last_heartbeat_age_sec: float | None = Field(
        default=None, description="Calculated age of last recorded heartbeat in seconds"
    )
