"""
[POS] app/schemas/assignment_sweep.py
[INPUT] pydantic
[OUTPUT] Quoted-key secret assignment sweep request and response DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssignmentSweepFindingDTO(BaseModel):
    """Individual sensitive assignment detected in content."""

    key_name: str = Field(..., description="Matched credential key or identifier")
    key_family: str = Field(..., description="Classification of credential key family")
    raw_matched_line: str = Field(..., description="Source line or context containing match")
    value_preview: str = Field(..., description="Masked preview of assigned value")
    format_kind: str = Field(..., description="Syntactic pattern detected: quoted_json, env_bracket, etc.")
    is_exempt: bool = Field(default=False, description="Whether this finding is exempted (e.g. local dev DSN)")
    exemption_reason: str | None = Field(default=None, description="Explanation for exemption if applicable")


class SweepTextRequestDTO(BaseModel):
    """Payload to sweep text, config, or environment variables for secret assignments."""

    content: str = Field(..., description="Source code, configuration, or .env text content to sweep")


class AssignmentSweepReportDTO(BaseModel):
    """Comprehensive sweep audit report evaluating text content or config files."""

    total_lines_scanned: int = Field(..., description="Number of text lines processed")
    findings: list[AssignmentSweepFindingDTO] = Field(
        default_factory=list, description="List of detected sensitive findings"
    )
    verdict: str = Field(..., description="Aggregated risk verdict: clean, suspected_leak, or exempted_local_dev")
    active_leaks_count: int = Field(..., description="Count of non-exempt active leaks detected")
    exempted_count: int = Field(..., description="Count of legitimately exempted local dev items")


class AuditDatabaseUrlRequestDTO(BaseModel):
    """Payload to evaluate a database connection URL."""

    raw_url: str = Field(..., min_length=1, description="Database connection URL to evaluate")


class DatabaseUrlAuditResultDTO(BaseModel):
    """Detailed compliance and risk assessment for a database connection URL."""

    raw_url: str = Field(..., description="Masked or original database URL")
    scheme: str = Field(..., description="Database protocol scheme, e.g. postgres, mysql, mongodb")
    host: str = Field(..., description="Extracted target host or domain")
    user: str = Field(..., description="Extracted username credential")
    is_loopback: bool = Field(..., description="Whether host is loopback (localhost or 127.0.0.1)")
    is_default_credential: bool = Field(..., description="Whether credentials match standard development defaults")
    is_exempt: bool = Field(..., description="Whether URL is exempted from leak blocking")
    audit_reason: str = Field(..., description="Detailed rationale of classification and risk verdict")


class CheckCleanContentRequestDTO(BaseModel):
    """Payload for quick boolean safety check of content."""

    content: str = Field(..., description="Text content to verify")


class CheckCleanContentResponseDTO(BaseModel):
    """Quick boolean safety verification response."""

    is_clean: bool = Field(..., description="Whether content is free of active unexempted credential leaks")
    verdict: str = Field(..., description="Aggregated risk verdict")
    active_leaks_count: int = Field(..., description="Count of active unexempted leaks found")
