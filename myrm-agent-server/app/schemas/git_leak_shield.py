"""Pydantic schemas for Zero-Trust Credential Isolation and Git Leakage Shield.

[INPUT]
None.

[OUTPUT]
DTO models for git diff scanning, pre-commit leak validation, and outbound text redaction.

[POS]
Server schemas. Exposes typed contracts for verifying Git operations and scrubbing
credentials from logs and messages before leaving the sandbox.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SecretMatchDto(BaseModel):
    """Details of a detected credential leak."""

    model_config = ConfigDict(extra="forbid")

    secret_type: str = Field(..., description="Classification category of the secret")
    pattern_name: str = Field(..., description="Name of the matching pattern rule")
    line_number: int = Field(..., description="Line number where secret was detected")
    masked_snippet: str = Field(..., description="Safe masked representation of the secret")
    suggested_env_var: str = Field(..., description="Recommended environment variable name")
    file_path: str = Field(..., description="Source file or diff identifier")


class GitDiffScanRequest(BaseModel):
    """Payload to scan a unified git diff for credential leaks."""

    model_config = ConfigDict(extra="forbid")

    diff_content: str = Field(..., description="Unified git diff text to inspect")
    file_path: str = Field(default="git_diff", description="Target file name or path")


class GitDiffScanResponse(BaseModel):
    """Results of a git diff scan."""

    model_config = ConfigDict(extra="forbid")

    has_leak: bool = Field(..., description="True if any credential leak was detected")
    findings: list[SecretMatchDto] = Field(default_factory=list, description="Detected credential findings")
    scanned_lines_count: int = Field(..., description="Number of added lines scanned")
    summary: str = Field(..., description="Summary verdict message")


class PreCommitCheckRequest(BaseModel):
    """Payload to check whether a git commit command is safe to execute."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="Bash command string to inspect")
    diff_content: str | None = Field(default=None, description="Staged diff content if available")


class PreCommitCheckResponse(BaseModel):
    """Decision on whether git commit or push is permitted."""

    model_config = ConfigDict(extra="forbid")

    blocked: bool = Field(..., description="True if the git command was blocked due to secret leak")
    reason: str = Field(..., description="Justification for the decision")
    findings: list[SecretMatchDto] = Field(default_factory=list, description="Violating credential findings")


class RedactTextRequest(BaseModel):
    """Payload to redact sensitive credentials from outbound text or logs."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Raw text to be scrubbed")


class RedactTextResponse(BaseModel):
    """Scrubbed text result and telemetry."""

    model_config = ConfigDict(extra="forbid")

    redacted_text: str = Field(..., description="Text with sensitive tokens masked")
    redactions_count: int = Field(..., description="Number of credential instances redacted")
    detected_types: list[str] = Field(default_factory=list, description="List of detected credential types")
