"""
[POS] app/schemas/browser_human_handoff.py
[INPUT] pydantic
[OUTPUT] InspectPageSafetyRequest, HandoffInterceptionResponse, InspectPageSafetyResponse, AcquireBrowserLeaseRequest, ReleaseBrowserLeaseRequest, BrowserProfileLeaseResponse, ResolveHandoffRequest, BrowserHumanHandoffMetricsResponse

Pydantic schemas for Browser Human Handoff Gate Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InspectPageSafetyRequest(BaseModel):
    """Payload to inspect a browser DOM for anti-bot captchas and empty corruptions."""

    html_or_dom: str = Field(..., description="Raw HTML or extracted DOM representation")
    url: str = Field(default="", description="Source page URL")


class HandoffInterceptionResponse(BaseModel):
    """Details of a triggered or cleared human handoff gate."""

    interception_id: str = Field(..., description="Unique interception identifier")
    trigger_type: str | None = Field(default=None, description="Trigger reason code if intercepted")
    matched_selector: str = Field(..., description="Matched selector or regex pattern")
    is_handoff_required: bool = Field(..., description="Whether automation must suspend for human takeover")
    explanation: str = Field(..., description="Human-readable decision explanation")
    is_resolved: bool = Field(..., description="Whether a human operator has completed the challenge")
    timestamp: float = Field(..., description="Unix timestamp of decision")


class DOMContentHealthResponse(BaseModel):
    """Health diagnostic of extracted DOM text completeness."""

    url: str = Field(..., description="Inspected page URL")
    content_length: int = Field(..., description="Extracted visible text length in characters")
    node_count: int = Field(..., description="Number of DOM elements/tags")
    is_corrupted_zero_content: bool = Field(..., description="Whether DOM exhibits silent empty whiteout")
    diagnosis: str = Field(..., description="Diagnostic summary")
    timestamp: float = Field(..., description="Unix timestamp of evaluation")


class InspectPageSafetyResponse(BaseModel):
    """Combined safety and DOM health inspection outcome."""

    interception: HandoffInterceptionResponse
    health: DOMContentHealthResponse


class ResolveHandoffRequest(BaseModel):
    """Payload to resolve an outstanding human handoff gate."""

    interception_id: str = Field(..., description="ID of the pending handoff interception")


class AcquireBrowserLeaseRequest(BaseModel):
    """Payload to request an exclusive session lock on a logged-in browser profile."""

    profile_name: str = Field(..., description="Target browser profile identifier")
    consumer_id: str = Field(..., description="Consumer task or agent ID requesting the lease")
    ttl_seconds: float = Field(default=300.0, description="Lease time-to-live in seconds")


class ReleaseBrowserLeaseRequest(BaseModel):
    """Payload to release an existing browser profile lease."""

    lease_id: str = Field(..., description="Unique lease identifier")


class BrowserProfileLeaseResponse(BaseModel):
    """Details of a browser profile exclusive lease."""

    lease_id: str = Field(..., description="Unique lease identifier")
    profile_name: str = Field(..., description="Associated browser profile name")
    consumer_id: str = Field(..., description="Consumer task or agent identifier holding lease")
    acquired_at: float = Field(..., description="Unix timestamp of acquisition")
    ttl_seconds: float = Field(..., description="TTL validity duration")
    status: str = Field(..., description="Status (AVAILABLE, LEASED, EXPIRED, RELEASED)")


class BrowserHumanHandoffMetricsResponse(BaseModel):
    """Metrics snapshot for browser human handoff operations."""

    captcha_interceptions_total: int
    confirm_screens_intercepted_total: int
    zero_content_corruptions_detected_total: int
    browser_leases_granted_total: int
    browser_leases_released_total: int
    handoffs_resolved_total: int
