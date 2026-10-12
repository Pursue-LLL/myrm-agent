"""Pydantic schemas for knowledge graph pre-extraction content screening and anti-poisoning API.

[INPUT]
- pydantic.BaseModel, ConfigDict, Field
- time

[OUTPUT]
- ThreatFindingDTO: Detail of individual detected injection vector
- ScreenContentRequestDTO: Request payload to evaluate text candidate
- ScreenContentResponseDTO: Response payload with verdict, findings, and sanitized text
- ScreeningAuditRecordDTO: Security audit entry representation
- ScreeningAuditListResponseDTO: Response containing historical security audit entries

[POS]
Data transfer contracts between frontend UI and server-side knowledge graph screening service.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class ThreatFindingDTO(BaseModel):
    """Identified threat or anomaly detail."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., description="Classification category (hidden_html_instruction, etc.)")
    matched_pattern: str = Field(..., description="Pattern identifier")
    snippet: str = Field(..., description="Excerpt of suspect content")
    position: int = Field(ge=0, description="Character offset")
    risk_level: str = Field(..., description="Severity level: 'high' or 'medium'")
    description: str = Field(..., description="Explanation of why flagged")


class ScreenContentRequestDTO(BaseModel):
    """Request payload to screen candidate text before knowledge graph extraction."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="Raw text to evaluate")
    source_uri: str = Field(default="", description="Origin URL or file path")
    sanitize_if_possible: bool = Field(default=True, description="Attempt sanitizing comments and zero-width chars")


class ScreenContentResponseDTO(BaseModel):
    """Response payload containing screening verdict and sanitized content."""

    model_config = ConfigDict(extra="forbid")

    verdict: str = Field(..., description="Screening verdict (clean, sanitized, poison_blocked)")
    is_blocked: bool = Field(..., description="Whether content is blocked from entering graph memory")
    findings: list[ThreatFindingDTO] = Field(default_factory=list, description="All identified threat vectors")
    original_length: int = Field(ge=0, description="Input length in characters")
    sanitized_content: str = Field(..., description="Sanitized content ready for extraction if unblocked")
    risk_score: float = Field(ge=0.0, le=1.0, description="Composite risk score (0.0=safe, 1.0=critical)")


class ScreeningAuditRecordDTO(BaseModel):
    """Historical security audit log entry."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(...)
    timestamp: float = Field(default_factory=time.time)
    source_uri: str = Field(default="")
    verdict: str = Field(...)
    risk_score: float = Field(ge=0.0, le=1.0)
    findings_count: int = Field(ge=0)
    findings_summary: list[str] = Field(default_factory=list)
    sanitized_applied: bool = Field(default=False)


class ScreeningAuditListResponseDTO(BaseModel):
    """List response of security screening audit records."""

    model_config = ConfigDict(extra="forbid")

    records: list[ScreeningAuditRecordDTO] = Field(default_factory=list)
    total_count: int = Field(ge=0)
