"""
[POS] app/schemas/memory_post_fetch_screening.py
[INPUT] pydantic
[OUTPUT] ScreeningPathModeEnum, PassageVerdictStatusEnum, MemoryPassageItem, PassageAuditVerdictDTO, PostFetchScreeningRequest, PostFetchScreeningResponse, ScreeningPolicyUpdateRequest, ScreeningMetricsResponse

Pydantic schemas for memory retrieval post-fetch injection screening suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ScreeningPathModeEnum(StrEnum):
    """Screening path mode enumeration."""

    JEV_AND_LOCAL = "jev+local"
    LOCAL_ONLY = "local-only"
    NONE = "none"


class PassageVerdictStatusEnum(StrEnum):
    """Passage verdict status classification."""

    CLEAN = "clean"
    TOXIC = "toxic"
    FAIL_OPEN = "fail_open"


class MemoryPassageItem(BaseModel):
    """Schema representing an individual candidate memory passage."""

    passage_id: str = Field(..., min_length=1, max_length=128, description="Unique passage identifier.")
    content: str = Field(..., description="Text content retrieved from memory store.")
    source_uri: str = Field(default="", description="Original reference URI or source identifier.")
    relevance_score: float = Field(default=0.0, description="Vector/Lexical relevance score.")
    created_at: str = Field(default="", description="ISO timestamp of passage acquisition.")


class QuarantinedPassageReportSchema(BaseModel):
    """Audit report for an isolated toxic passage."""

    passage_id: str = Field(..., description="ID of the quarantined passage.")
    source_uri: str = Field(default="", description="Source origin of the passage.")
    snippet: str = Field(..., description="Truncated safe snippet of the toxic content.")
    rejection_reason: str = Field(..., description="Specific reason for isolation.")
    pathway_used: ScreeningPathModeEnum = Field(..., description="Screening pipeline pathway used.")
    threat_category: str = Field(..., description="Classification category of the detected threat.")
    detected_at: str = Field(..., description="ISO timestamp of detection.")


class ScreenMemoryPassagesRequest(BaseModel):
    """Request payload for screening retrieved memory passages."""

    passages: list[MemoryPassageItem] = Field(..., max_length=100, description="List of passages to screen.")


class ScreenMemoryPassagesResponse(BaseModel):
    """Response containing sanitized passages and quarantine reports."""

    total_evaluated: int = Field(..., ge=0, description="Total passages screened.")
    clean_passages: list[MemoryPassageItem] = Field(..., description="Approved passages safe for LLM context.")
    quarantined_reports: list[QuarantinedPassageReportSchema] = Field(
        default_factory=list, description="Reports for toxic passages that were quarantined."
    )
    pathway_taken: ScreeningPathModeEnum = Field(..., description="Screening pathway used.")
    latency_ms: float = Field(..., ge=0.0, description="Screening execution time in milliseconds.")
    degradation_reason: str = Field(default="", description="Reason for degradation if applicable.")


class MemoryScreeningPolicyUpdateRequest(BaseModel):
    """Request payload for dynamically updating the memory screening policy."""

    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence threshold.")
    remote_timeout_seconds: float = Field(default=3.5, ge=0.1, le=30.0, description="Timeout budget in seconds.")
    remote_scorer_enabled: bool = Field(default=True, description="Enable remote model scoring.")
    quarantine_toxic_passages: bool = True
    enable_url_exfiltration_scan: bool = True
    enable_command_risk_scan: bool = True


class MemoryScreeningMetricsResponse(BaseModel):
    """Operational telemetry and detection metrics for memory screening."""

    total_passages_evaluated: int = Field(..., ge=0, description="Cumulative count of screened passages.")
    clean_passages_count: int = Field(..., ge=0, description="Passages passed into context.")
    quarantined_passages_count: int = Field(..., ge=0, description="Toxic passages blocked and isolated.")
    avg_latency_ms: float = Field(..., ge=0.0, description="Average screening latency in milliseconds.")
    jev_path_count: int = Field(..., ge=0, description="Count of requests evaluated via jev+local pathway.")
    local_path_count: int = Field(..., ge=0, description="Count of requests evaluated via local-only pathway.")
