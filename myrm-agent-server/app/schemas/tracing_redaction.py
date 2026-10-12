"""Pydantic schemas for Tracing Sensitive Data Redactor across all execution paths.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for sanitizing trace spans across success, error, streaming, retry, and resume paths.

[POS]
- Server schemas for OpenAI-Agents-JS #1970 sensitive data redaction.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionPathTypeDto(StrEnum):
    """Execution path where a trace or telemetry span was captured."""

    SUCCESS = "success"
    ERROR = "error"
    STREAMING = "streaming"
    RETRY = "retry"
    RESUME = "resume"


class TracingOptOutModeDto(StrEnum):
    """Opt-out handling mode for tracing and telemetry."""

    ALLOW_TRACING = "allow_tracing"
    REDACT_MANDATORY = "redact_mandatory"
    DROP_TRACE = "drop_trace"


class SanitizeTraceSpanRequest(BaseModel):
    """Request payload for redacting sensitive values from a trace span."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(..., description="Unique trace session identifier")
    span_id: str = Field(..., description="Unique span identifier")
    path_type: ExecutionPathTypeDto = Field(..., description="Execution path origin")
    payload: dict[str, object] = Field(
        default_factory=dict, description="Arbitrary span payload data"
    )
    raw_error: str | None = Field(
        default=None, description="Raw error or stack trace message if present"
    )
    opt_out_requested: bool = Field(
        default=False,
        description="Whether the user or tenant requested tracing opt-out",
    )
    opt_out_mode: TracingOptOutModeDto | None = Field(
        default=None, description="Optional override policy for opt-out handling"
    )


class SanitizeTraceSpanResponse(BaseModel):
    """Response payload containing redacted trace span."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    span_id: str
    path_type: ExecutionPathTypeDto
    sanitized_payload: dict[str, object]
    sanitized_error: str | None = None
    is_dropped: bool = False
    redaction_count: int = 0
    policy_applied: str
