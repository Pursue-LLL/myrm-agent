"""Pydantic schemas for Memory Defense Ingestion Firewall and PII Sanitization Suite.

[INPUT]
- None (Self-contained Pydantic schemas)

[OUTPUT]
- DefenseInspectRequest, DefenseInspectResponse, ExemptionAddRequest
- ExemptionResponse, ExemptionListResponse, PatternCatalogResponse

[POS]
Schema definitions for memory defense firewall, sanitization actions, and exemption rules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DefenseInspectRequest(BaseModel):
    """Request payload for evaluating memory content before ingestion."""

    text: str = Field(..., description="Raw inbound memory text candidate")
    default_action: str = Field(
        default="REDACT",
        description="Default defense action if sensitive tokens found: ALLOW, REDACT, or BLOCK",
    )
    blocked_categories: list[str] = Field(
        default_factory=list,
        description="Explicit categories to strictly BLOCK rather than redact",
    )


class DetectionMatchItem(BaseModel):
    """Detail of a single sensitive pattern matched in inbound text."""

    pattern_id: str = Field(..., description="Pattern identifier")
    pattern_name: str = Field(..., description="Human-readable pattern title")
    category: str = Field(..., description="Sensitive category string")
    start: int = Field(..., description="Start character index")
    end: int = Field(..., description="End character index")
    matched_preview: str = Field(..., description="Truncated or safe preview of matched token")
    replacement_tag: str = Field(..., description="Redaction placeholder inserted")


class DefenseInspectResponse(BaseModel):
    """Outcome of pre-ingestion memory defense evaluation."""

    action_taken: str = Field(..., description="Final decision: ALLOW, REDACT, or BLOCK")
    is_admitted: bool = Field(..., description="Whether content is admitted for memory persistence")
    sanitized_text: str = Field(..., description="Sanitized text ready for vector/database storage")
    original_length: int = Field(..., description="Original text character length")
    sanitized_length: int = Field(..., description="Sanitized text character length")
    matches: list[DetectionMatchItem] = Field(
        default_factory=list,
        description="List of detected sensitive token matches",
    )
    audit_id: str = Field(..., description="Unique audit event record identifier")
    timestamp: float = Field(..., description="Evaluation timestamp")


class ExemptionAddRequest(BaseModel):
    """Request payload to register a token or content hash in false-positive whitelist."""

    token_or_content: str = Field(..., description="Exact token string or text to whitelist")


class ExemptionResponse(BaseModel):
    """Status returned after adding or removing an exemption entry."""

    success: bool = Field(..., description="Whether operation succeeded")
    token_or_content: str = Field(..., description="Target token or content string")


class ExemptionListResponse(BaseModel):
    """Listing of all active false-positive exemption entries."""

    exemptions: list[str] = Field(default_factory=list, description="Active whitelist tokens and hashes")


class PatternCatalogItem(BaseModel):
    """Specification of a sensitive pattern supported by the firewall."""

    pattern_id: str = Field(..., description="Pattern identifier")
    name: str = Field(..., description="Pattern title")
    category: str = Field(..., description="Pattern category")
    replacement_tag: str = Field(..., description="Default redaction tag")
    description: str = Field(..., description="Pattern description")


class PatternCatalogResponse(BaseModel):
    """Response containing the full catalog of built-in sensitive detection patterns."""

    total_count: int = Field(..., description="Total count of active patterns")
    patterns: list[PatternCatalogItem] = Field(default_factory=list, description="Pattern list")
