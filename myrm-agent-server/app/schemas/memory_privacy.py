"""
[POS] app/schemas/memory_privacy.py
[INPUT] pydantic
[OUTPUT] SecretFindingDTO, PrivacyCheckRequestDTO, PrivacyCheckResponseDTO, SanitizeContentRequestDTO, SanitizeContentResponseDTO, PrivacyConfigDTO

Pydantic schemas for memory privacy boundary gate, sensitive credential detection, and safe redaction.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SecretFindingDTO(BaseModel):
    """Data transfer object describing a detected sensitive credential."""

    model_config = ConfigDict(extra="forbid")

    violation_type: str = Field(..., description="Taxonomy classification of the violation")
    snippet_masked: str = Field(..., description="Masked snippet safe for telemetry and review")
    category: str = Field(..., description="Human-readable category name")
    line_number: int = Field(..., ge=1, description="Line number of detected secret")


class PrivacyCheckRequestDTO(BaseModel):
    """Payload to inspect candidate memory text before persistence."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, description="Candidate textual memory payload")
    source_path: str | None = Field(default=None, description="Optional source file or resource path")


class PrivacyCheckResponseDTO(BaseModel):
    """Inspection outcome of memory privacy boundary evaluation."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(..., description="True if memory candidate passes privacy policy")
    sensitivity_level: str = Field(..., description="Classification: public, internal, sensitive, critical_secret")
    findings: list[SecretFindingDTO] = Field(default_factory=list, description="Detected violation findings")
    redacted_content: str = Field(..., description="Content with secrets substituted by semantic masks")
    violation_reason: str | None = Field(default=None, description="Reason if candidate was rejected")


class SanitizeContentRequestDTO(BaseModel):
    """Payload to sanitize text by redacting secrets without raising hard rejections."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, description="Raw text requiring secret scrubbing")
    source_path: str | None = Field(default=None, description="Optional source path")


class SanitizeContentResponseDTO(BaseModel):
    """Response containing sanitized text with secrets scrubbed."""

    model_config = ConfigDict(extra="forbid")

    sanitized_content: str = Field(..., description="Scrubbed and masked content")
    was_modified: bool = Field(..., description="True if secrets were scrubbed")


class PrivacyConfigDTO(BaseModel):
    """Telemetry DTO representing active memory privacy gate configuration."""

    model_config = ConfigDict(extra="forbid")

    allow_patterns: list[str] = Field(default_factory=list, description="Explicitly whitelisted paths/patterns")
    exclude_patterns: list[str] = Field(default_factory=list, description="Excluded paths/patterns")
    block_on_critical: bool = Field(..., description="Whether critical secrets trigger hard veto")
    strict_mode: bool = Field(..., description="Whether any sensitive finding causes rejection")
