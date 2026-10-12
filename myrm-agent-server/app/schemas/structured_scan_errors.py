"""Pydantic DTO schemas for Structured JSON Scan Failure Errors.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for scan failure emission, classification, and remediation guidance contracts.

[POS]
- Server schemas. Exposes typed contracts for machine-readable scanner error reporting.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmitScanFailureRequest(BaseModel):
    """Request payload to construct a structured scan error envelope."""

    model_config = ConfigDict(extra="forbid")

    scan_id: str = Field(..., description="Unique scan run identifier")
    target_path_or_url: str = Field(
        ..., description="Filesystem directory or repository URL targeted by scan"
    )
    scanner_engine: str = Field(
        ..., description="Scanner binary identifier (e.g. osv-scanner, trivy, semgrep)"
    )
    exit_code: int | None = Field(
        default=None, description="Process exit code if process completed"
    )
    stderr: str = Field(default="", description="Raw standard error output from scanner")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Diagnostic tags (e.g. branch, commit, worker_id)"
    )


class ClassifyScanFailureRequest(BaseModel):
    """Request payload to classify exit code and stderr without full scan context."""

    model_config = ConfigDict(extra="forbid")

    exit_code: int | None = Field(default=None, description="Process exit code")
    stderr: str = Field(default="", description="Raw standard error output snippet")


class ScanErrorContextDto(BaseModel):
    """Execution context details for failed scan."""

    model_config = ConfigDict(extra="forbid")

    scan_id: str = Field(..., description="Scan identifier")
    target_path_or_url: str = Field(..., description="Target repository or path")
    scanner_engine: str = Field(..., description="Scanner tool name")
    exit_code: int | None = Field(default=None, description="Exit code")
    timestamp: float = Field(..., description="Epoch timestamp of failure")
    raw_stderr_snippet: str | None = Field(
        default=None, description="Truncated stderr snippet"
    )
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Metadata tags"
    )


class ScanRemediationAdviceDto(BaseModel):
    """Prescriptive remediation instructions for pipeline or engineer."""

    model_config = ConfigDict(extra="forbid")

    suggested_action: str = Field(
        ..., description="RETRY, SKIP, BLOCK_PIPELINE, or ESCALATE_HUMAN"
    )
    remediation_steps: list[str] = Field(
        default_factory=list, description="Ordered step-by-step resolution advice"
    )
    retryable: bool = Field(
        ..., description="Whether automated orchestrator should safely retry"
    )
    backoff_seconds: float | None = Field(
        default=None, description="Recommended retry backoff delay in seconds"
    )


class StructuredScanErrorEnvelopeDto(BaseModel):
    """Complete machine-readable JSON error contract for failed scans."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(..., description="Categorized SCAN_* error code")
    message: str = Field(..., description="Human-readable root cause explanation")
    severity: str = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL")
    context: ScanErrorContextDto = Field(..., description="Execution environment context")
    remediation: ScanRemediationAdviceDto = Field(
        ..., description="Actionable remediation advice"
    )


class ClassifiedFailureDto(BaseModel):
    """Failure classification outcome."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(..., description="SCAN_* error code")
    message: str = Field(..., description="Diagnostic explanation")
    suggested_action: str = Field(..., description="RETRY, SKIP, BLOCK_PIPELINE, ESCALATE_HUMAN")
    remediation_steps: list[str] = Field(
        default_factory=list, description="Suggested resolution steps"
    )
    retryable: bool = Field(..., description="True if retryable")
    backoff_seconds: float | None = Field(default=None, description="Backoff delay")
