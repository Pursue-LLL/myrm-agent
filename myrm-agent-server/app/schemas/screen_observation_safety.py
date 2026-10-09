"""Pydantic V2 DTO schemas for screen observation memory safety gate and anti-injection.

[INPUT]
- typing: Literal, Optional, List
- pydantic: BaseModel, Field, ConfigDict

[OUTPUT]
- IngestScreenObservationRequest, ScreenObservationSafetyResponse
- ScreenSafetyAuditItemDTO, ScreenSafetyAuditListResponse

[POS]
Server data transfer layer for ChatGPT Desktop Skysight-style screen observation
safety, boundary isolation, descriptive fact validation, and promotion gate (Topic 01 Item 85).
Strict typing applied: No `any` types allowed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ObservationSourceType = Literal[
    "ax_tree",
    "ocr_text",
    "screenshot_summary",
    "browser_dom",
    "terminal_output",
]

PromotionStatus = Literal[
    "transient_observation",
    "candidate_pattern",
    "promoted_preference",
    "rejected_injection",
]


class IngestScreenObservationRequest(BaseModel):
    """Request payload for processing raw screen observation evidence."""

    model_config = ConfigDict(extra="forbid")

    source_type: ObservationSourceType = Field(
        ...,
        description="Type of screen/desktop observation source.",
    )
    raw_text: str = Field(
        ...,
        description="Raw un-trusted text captured from screen/OCR/DOM.",
    )
    extracted_statement: str = Field(
        ...,
        description="Candidate factual statement extracted by observer.",
    )
    app_name: str = Field(
        default="UnknownApp",
        description="Active desktop application name.",
    )
    window_title: str = Field(
        default="Untitled",
        description="Active desktop window title.",
    )
    session_id: str = Field(
        default="default_session",
        description="Identifier of current working session.",
    )
    app_bundle_id: str = Field(
        default="",
        description="Optional OS application bundle identifier.",
    )


class ScreenObservationSafetyResponse(BaseModel):
    """Response payload detailing security boundary, syntax validation, and gate verdict."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Unique audit ledger identifier.")
    is_safe: bool = Field(..., description="Whether observation was deemed safe from prompt injection.")
    risk_score: float = Field(..., description="Calculated injection risk score between 0.0 and 1.0.")
    detected_injection_patterns: list[str] = Field(
        default_factory=list,
        description="List of detected injection signature names.",
    )
    promotion_status: PromotionStatus = Field(
        ...,
        description="Gatekeeper status: transient_observation, candidate_pattern, promoted_preference, or rejected_injection.",
    )
    is_promoted: bool = Field(..., description="Whether the fact was promoted to stable preference.")
    final_statement: str = Field(..., description="Final admitted and syntax-normalized factual statement.")
    imperative_detected: bool = Field(..., description="Whether imperative syntax was detected and rewritten.")
    explanation: str = Field(..., description="Human-readable decision explanation.")
    isolated_prompt_preview: str = Field(..., description="Preview snippet of inert wrapped evidence.")


class ScreenSafetyAuditItemDTO(BaseModel):
    """Audit ledger record item for monitoring and compliance."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(..., description="Unique record identifier.")
    session_id: str = Field(..., description="Session identifier.")
    app_name: str = Field(..., description="Source application name.")
    fact_statement: str = Field(..., description="Admitted or attempted fact statement.")
    promotion_status: PromotionStatus = Field(..., description="Gate decision status.")
    risk_score: float = Field(..., description="Injection risk score.")
    imperative_detected: bool = Field(..., description="Whether imperative syntax was detected.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


class ScreenSafetyAuditListResponse(BaseModel):
    """Response payload containing recent screen observation safety audit records."""

    model_config = ConfigDict(extra="forbid")

    records: list[ScreenSafetyAuditItemDTO] = Field(
        default_factory=list,
        description="List of recent audit records.",
    )
    total_count: int = Field(..., description="Total count of returned audit records.")
