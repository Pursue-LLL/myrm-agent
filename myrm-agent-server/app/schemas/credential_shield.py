"""Pydantic DTO schemas for Credential Stdin Pipelining & Process Leakage Shield.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for command analysis, stdin pipelining specs, and display sanitization.

[POS]
- Server schemas. Exposes typed contracts for process table leakage defense.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeCommandLineRequest(BaseModel):
    """Request payload to analyze a command for exposed plain-text credentials."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="Full command line string to inspect for argv secrets")


class ProcessLeakageAnalysisDto(BaseModel):
    """Outcome of command line credential analysis."""

    model_config = ConfigDict(extra="forbid")

    is_safe_for_process_table: bool = Field(
        ..., description="True if command does not leak plain-text credentials in argv"
    )
    risk_level: str = Field(..., description="SAFE, SUSPICIOUS, or HIGH_RISK_PROCESS_TABLE_EXPOSURE")
    detected_leaks: list[str] = Field(
        default_factory=list, description="Categories of secrets detected in argv"
    )
    suggested_rewritten_command: str | None = Field(
        default=None, description="Rewritten command with redacted credentials"
    )
    audit_notes: str = Field(default="", description="Analysis rationale and remediation advice")


class PipelineCommandRequest(BaseModel):
    """Request payload to transform a command into an immune stdin-pipelined execution spec."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="Raw command with potential secrets to pipeline via stdin")


class PipelinedCommandDto(BaseModel):
    """Sanitized pipelined command specification."""

    model_config = ConfigDict(extra="forbid")

    original_command: str = Field(..., description="Original requested command")
    sanitized_argv: list[str] = Field(
        ..., description="Clean argv list free of secret tokens, suitable for process table"
    )
    has_stdin_payload: bool = Field(
        ..., description="Whether credentials must be fed via stdin stream"
    )
    transport_mode: str = Field(
        ..., description="STDIN_PIPELINE, STDIN_CONFIG_STREAM, or ENV_VARIABLE_SECURE"
    )
    sanitized_display_cmd: str = Field(
        ..., description="Redacted command string safe for audit logs and UI display"
    )
    detected_secret_patterns: list[str] = Field(
        default_factory=list, description="Identified secret patterns removed from argv"
    )


class SanitizeDisplayCommandRequest(BaseModel):
    """Request payload to redact credentials from a command string for safe logging."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="Raw command string")


class SanitizedDisplayResponse(BaseModel):
    """Sanitized command string response."""

    model_config = ConfigDict(extra="forbid")

    sanitized_command: str = Field(..., description="Redacted command string safe for public display")
