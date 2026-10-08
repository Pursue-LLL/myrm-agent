"""Pydantic schemas and DTOs for Thinking Block Sanitizer & Prompt Contamination Shield.

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- ThinkingSanitizerConfigDTO: sanitizer options
- SanitizeTextRequest, SanitizationResultDTO: text sanitization and its result
- CheckUsableSummaryRequest, UsableSummaryCheckResponse: usable-summary check

[POS]
API contracts of the thinking block sanitizer, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ThinkingSanitizerConfigDTO(BaseModel):
    """Configuration DTO for ThinkingBlockSanitizer execution."""

    min_usable_chars: int = Field(
        default=10,
        ge=1,
        description="Minimum character length threshold for cleaned summary usability",
    )
    strip_planning_leadins: bool = Field(
        default=True,
        description="Whether to scrub meta-talk and planning lead-in sentences",
    )
    preserve_post_close_text: bool = Field(
        default=True,
        description="Whether to preserve text following orphan close tags like </think>",
    )
    drop_unclosed_tags: bool = Field(
        default=True,
        description="Whether to truncate content starting at unclosed open thinking tags",
    )
    extra_planning_patterns: list[str] = Field(
        default_factory=list,
        description="Optional additional regex strings for stripping custom planning lead-ins",
    )


class SanitizationResultDTO(BaseModel):
    """Telemetry and output DTO for thinking block sanitization."""

    original_text: str = Field(description="Raw original text before sanitization")
    cleaned_text: str = Field(description="Scrubbed and normalized output text")
    has_thinking_markers: bool = Field(description="Whether any thinking or draft markers were found")
    has_unclosed_tags: bool = Field(description="Whether unclosed open tags were detected")
    stripped_markers_count: int = Field(description="Total count of markers or blocks scrubbed")
    is_usable: bool = Field(description="Whether the output satisfies downstream usability criteria")
    rejection_reason: str | None = Field(default=None, description="Diagnostic reason if marked unusable")


class SanitizeTextRequest(BaseModel):
    """Request payload to sanitize text from reasoning channels."""

    text: str = Field(description="Raw text to sanitize")
    config: ThinkingSanitizerConfigDTO | None = Field(
        default=None,
        description="Optional custom sanitization configuration",
    )


class CheckUsableSummaryRequest(BaseModel):
    """Request payload for bi-directional egress usable summary evaluation."""

    text: str = Field(description="Candidate summary text to evaluate for egress injection")
    config: ThinkingSanitizerConfigDTO | None = Field(
        default=None,
        description="Optional custom sanitization configuration",
    )


class UsableSummaryCheckResponse(BaseModel):
    """Response payload for bi-directional egress usable summary evaluation."""

    is_usable: bool = Field(description="Whether the candidate summary is safe and usable")
    summary: str | None = Field(default=None, description="Cleaned summary text, or None if omitted")
    rejection_reason: str | None = Field(default=None, description="Reason if candidate was omitted")
