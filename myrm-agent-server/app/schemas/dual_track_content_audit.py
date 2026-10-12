"""
[POS] app/schemas/dual_track_content_audit.py
[INPUT] pydantic
[OUTPUT] ContentRiskLevelEnum, ViolationCategoryEnum, CircuitBreakerActionEnum, MirrorChunkRequest, AuditVerdictResponse, CircuitBreakerSignalResponse, MirrorChunkResponse, ScanTextRequest, ScanTextResponse, BreakerStatusResponse, ResetBreakerRequest, ResetBreakerResponse, DualTrackMetricsResponse

Pydantic schemas for Decoupled Async Dual-Track Content Audit & Realtime Circuit Breaker Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class ContentRiskLevelEnum(StrEnum):
    """Risk level classification for content audit."""

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    CRITICAL = "CRITICAL"


class ViolationCategoryEnum(StrEnum):
    """Violation categories for sensitive and dangerous content."""

    NONE = "NONE"
    POLITICAL_SENSITIVE = "POLITICAL_SENSITIVE"
    TRADE_SECRET = "TRADE_SECRET"
    CREDENTIAL_LEAK = "CREDENTIAL_LEAK"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    FINANCIAL_CONFIDENTIAL = "FINANCIAL_CONFIDENTIAL"


class CircuitBreakerActionEnum(StrEnum):
    """Action dictated by circuit breaker."""

    PASS = "PASS"
    TRIP_AND_ABORT = "TRIP_AND_ABORT"
    WARN = "WARN"


class MirrorChunkRequest(BaseModel):
    """Request payload to asynchronously mirror a stream chunk for inspection."""

    session_id: str = Field(..., min_length=1, max_length=128, description="Target streaming session ID.")
    sequence_no: int = Field(..., ge=0, description="Sequential chunk index in stream.")
    text_chunk: str = Field(..., description="Chunk text content emitted by model or tool.")
    is_final: bool = Field(default=False, description="Whether this is the concluding chunk of the stream.")


class AuditVerdictResponse(BaseModel):
    """Compliance verdict on audited text content."""

    is_violation: bool = Field(..., description="True if text violates security or confidentiality policies.")
    risk_level: ContentRiskLevelEnum = Field(..., description="Evaluated risk severity.")
    category: ViolationCategoryEnum = Field(..., description="Classification category.")
    confidence: float = Field(..., description="Classifier confidence score.")
    matched_pattern: Optional[str] = Field(default=None, description="Matched substring or snippet.")
    reason: str = Field(..., description="Human-readable decision explanation.")


class CircuitBreakerSignalResponse(BaseModel):
    """Circuit breaker interruption payload to abort streaming conduit."""

    session_id: str = Field(..., description="Session identifier.")
    trigger_sequence_no: int = Field(..., description="Sequence number where breaker tripped.")
    action: CircuitBreakerActionEnum = Field(..., description="Circuit breaker action.")
    category: ViolationCategoryEnum = Field(..., description="Underlying violation category.")
    abort_frame: str = Field(..., description="Interruption frame injected into SSE stream.")
    reason: str = Field(..., description="Reason for aborting stream.")
    timestamp: float = Field(..., description="Trip timestamp.")


class MirrorChunkResponse(BaseModel):
    """Response returned upon processing a mirrored stream chunk."""

    verdict: AuditVerdictResponse = Field(..., description="Compliance evaluation outcome.")
    circuit_breaker_signal: Optional[CircuitBreakerSignalResponse] = Field(
        default=None, description="Signal to halt stream if tripped."
    )
    is_tripped: bool = Field(..., description="True if session circuit breaker is in tripped state.")


class ScanTextRequest(BaseModel):
    """Request to synchronously audit a static text payload."""

    text: str = Field(..., min_length=1, description="Text to scan for compliance violations.")


class ScanTextResponse(BaseModel):
    """Response for synchronous text compliance audit."""

    verdict: AuditVerdictResponse = Field(..., description="Audit verdict.")


class BreakerStatusResponse(BaseModel):
    """Current circuit breaker state of a session."""

    session_id: str = Field(..., description="Session identifier.")
    is_tripped: bool = Field(..., description="Whether circuit breaker is tripped.")
    signal: Optional[CircuitBreakerSignalResponse] = Field(default=None, description="Tripping signal details.")


class ResetBreakerRequest(BaseModel):
    """Request to reset a tripped session circuit breaker."""

    session_id: str = Field(..., min_length=1, description="Session ID to reset.")


class ResetBreakerResponse(BaseModel):
    """Response of circuit breaker reset operation."""

    session_id: str = Field(..., description="Session identifier.")
    was_reset: bool = Field(..., description="True if breaker was previously tripped and successfully cleared.")


class DualTrackMetricsResponse(BaseModel):
    """Operational metrics for dual-track out-of-band audit subsystem."""

    total_chunks_mirrored: int = Field(..., ge=0, description="Total stream chunks mirrored.")
    total_violations_detected: int = Field(..., ge=0, description="Total safety policy violations detected.")
    total_breakers_tripped: int = Field(..., ge=0, description="Total stream sessions aborted by breaker.")
    active_monitored_sessions: int = Field(..., ge=0, description="Active sessions being tracked.")
