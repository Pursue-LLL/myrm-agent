"""Pydantic schemas for Data Plane Injection Defense, Hardened Fencing, and Visual QuotedAsData.

[INPUT]
None.

[OUTPUT]
DTO models for external data fencing, two-plane injection detection, and visual trust badge projections.

[POS]
Server schemas. Exposes typed contracts for hardened data fence and QuotedAsData badge metadata.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class DataPlaneThreatFindingDto(BaseModel):
    """Specific threat signature detected and neutralized."""

    model_config = ConfigDict(extra="forbid")

    threat_type: str = Field(..., description="Classification category of detected threat")
    pattern_matched: str = Field(..., description="Pattern rule or signature matched")
    raw_snippet: str = Field(..., description="Raw text snippet that was flagged")
    sanitized_replacement: str = Field(..., description="Neutralized replacement token")


class FencePayloadRequest(BaseModel):
    """Payload to sanitize untrusted external data and wrap in structural fences."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(..., description="Raw third-party or tool-produced text")
    subject: str = Field(default="untrusted_content", description="Content domain subject (e.g. user_review, seller_policy)")
    source: str = Field(default="external_tool", description="Origin of the data payload")
    max_fenced_chars: int = Field(default=16000, description="Max character threshold before truncation")


class FencePayloadResponse(BaseModel):
    """Sanitized data payload with boundary tags and telemetry."""

    model_config = ConfigDict(extra="forbid")

    sanitized_text: str = Field(..., description="Cleaned, normalized, and defanged text")
    enclosed_payload: str = Field(..., description="XML/role-boundary wrapped payload ready for LLM prompt")
    subject: str = Field(..., description="Content domain subject")
    source: str = Field(..., description="Data origin")
    original_length: int = Field(..., description="Original raw character count")
    sanitized_length: int = Field(..., description="Sanitized character count")
    stripped_turns_count: int = Field(..., description="Count of defanged turn markers")
    removed_control_chars_count: int = Field(..., description="Count of stripped invisible/control characters")
    is_truncated: bool = Field(..., description="Whether content exceeded max_fenced_chars")
    findings: list[DataPlaneThreatFindingDto] = Field(default_factory=list, description="List of neutralized threats")
    sanitized_at: float = Field(default_factory=time.time, description="Unix timestamp of fencing")


class DetectInjectionRequest(BaseModel):
    """Payload to analyze text against user-plane or data-plane injection rules."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Text string to evaluate")
    plane: str = Field(default="data_plane", description="Target plane: 'user_plane' or 'data_plane'")


class DetectInjectionResponse(BaseModel):
    """Two-plane prompt injection analysis verdict."""

    model_config = ConfigDict(extra="forbid")

    plane: str = Field(..., description="Evaluated plane")
    is_suspicious: bool = Field(..., description="True if prompt injection attempt detected")
    risk_score: float = Field(..., description="Confidence risk score (0.0 to 1.0)")
    detected_rules: list[str] = Field(default_factory=list, description="Rules that matched")
    findings: list[DataPlaneThreatFindingDto] = Field(default_factory=list, description="Detailed threat snippets")
    analyzed_at: float = Field(default_factory=time.time, description="Timestamp of analysis")


class QuotedAsDataBadgeDto(BaseModel):
    """Metadata projection for frontend visual QuotedAsData trust badge."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(..., description="Content label displayed in badge (e.g. '用户评价')")
    source: str = Field(..., description="Source origin")
    sanitized_content: str = Field(..., description="Safe content to display")
    is_verified_untrusted_quote: bool = Field(default=True, description="True indicates third-party unendorsed quote")
    disclaimer: str = Field(..., description="Clarifying human-readable disclaimer banner")
