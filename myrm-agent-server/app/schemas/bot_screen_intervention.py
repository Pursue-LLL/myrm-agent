"""
[POS] app/schemas/bot_screen_intervention.py
[INPUT] pydantic
[OUTPUT] ClassifyElementRiskRequest, ClassifyElementRiskResponse, EvaluateScreenActionRequest, EvaluateScreenActionResponse, StartInterventionRequest, StartInterventionResponse, RecordInterventionEventRequest, InterventionEventResponse, SealEvidenceBundleRequest, InterventionEvidenceBundleResponse, VerifyScreenAssertionRequest, ScreenAssertionProbeResponse, BotScreenOperationalMetricsResponse

Pydantic schemas for Bot Screen Auditable Operational Control & Intervention Evidence.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClassifyElementRiskRequest(BaseModel):
    """Payload to classify screen element risk tier."""

    selector: str = Field(..., description="Target UI DOM or accessibility selector")
    label: str = Field(..., description="Visible button/input label or accessible name")
    action_type: str = Field(default="click", description="Type of intended UI interaction")


class ClassifyElementRiskResponse(BaseModel):
    """Result of screen element risk tier classification."""

    selector: str = Field(..., description="Selector classified")
    label: str = Field(..., description="Label evaluated")
    risk_tier: str = Field(..., description="Assigned risk tier: SAFE_READONLY, STANDARD_WRITE, HIGH_RISK_FINANCIAL, CRITICAL_ADMIN")


class EvaluateScreenActionRequest(BaseModel):
    """Payload evaluating intended screen action against least-privilege boundary rules."""

    action_id: str = Field(..., description="Unique action request ID")
    target_selector: str = Field(..., description="Target DOM or accessibility selector")
    action_type: str = Field(..., description="Action type: click, type, submit, etc.")
    label: str = Field(..., description="Human-readable label of the element")
    value_masked: str = Field(default="", description="Sanitized/masked input value if typing")
    risk_tier: str = Field(..., description="Declared or classified risk tier")


class EvaluateScreenActionResponse(BaseModel):
    """Operational gate decision on intended screen action."""

    action_id: str = Field(..., description="Action ID evaluated")
    decision: str = Field(..., description="Approval decision: APPROVED_AUTOMATIC, PENDING_HUMAN_APPROVAL, REJECTED, MANUAL_TAKEOVER_REQUIRED")
    reason: str = Field(..., description="Diagnostic justification for approval or takeover checkpoint")


class StartInterventionRequest(BaseModel):
    """Payload initiating a recorded human takeover intervention session."""

    session_id: str = Field(..., description="Active agent session ID")
    operator_id: str = Field(..., description="Human operator badge/identity ID")
    before_snapshot_hash: str = Field(..., description="SHA-256 hash of UI screen snapshot prior to takeover")


class StartInterventionResponse(BaseModel):
    """Result of starting human takeover session."""

    intervention_id: str = Field(..., description="Assigned takeover intervention session ID")
    session_id: str = Field(..., description="Target agent session ID")
    operator_id: str = Field(..., description="Operator badge ID")


class RecordInterventionEventRequest(BaseModel):
    """Payload capturing human operator keystroke/mouse input event."""

    intervention_id: str = Field(..., description="Active intervention ID")
    event_type: str = Field(..., description="Event type: mouse_click, keyboard_input, scroll")
    target_selector: str = Field(..., description="DOM selector interacted with")
    raw_data: str = Field(default="", description="Raw input data (scrubbed prior to storage)")


class InterventionEventResponse(BaseModel):
    """Sanitized record of human intervention event."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Type of event recorded")
    target_selector: str = Field(..., description="DOM selector")
    timestamp: float = Field(..., description="Unix timestamp of event")
    data_sanitized: str = Field(..., description="Sanitized/redacted data")


class SealEvidenceBundleRequest(BaseModel):
    """Payload sealing the cryptographic audit bundle at conclusion of human takeover."""

    intervention_id: str = Field(..., description="Target intervention ID to close")
    after_snapshot_hash: str = Field(..., description="SHA-256 hash of UI screen snapshot upon handover back to agent")


class InterventionEvidenceBundleResponse(BaseModel):
    """Sealed tamper-proof intervention evidence bundle."""

    session_id: str = Field(..., description="Agent session ID")
    intervention_id: str = Field(..., description="Takeover intervention ID")
    operator_id: str = Field(..., description="Operator badge ID")
    start_time: float = Field(..., description="Start timestamp")
    end_time: float = Field(..., description="End timestamp")
    before_snapshot_hash: str = Field(..., description="Pre-takeover snapshot SHA-256")
    after_snapshot_hash: str = Field(..., description="Post-takeover snapshot SHA-256")
    event_count: int = Field(..., description="Count of recorded intervention events")
    bundle_sha256: str = Field(..., description="Cryptographic SHA-256 anchor digest")
    is_tamper_evident: bool = Field(..., description="Integrity verification status")


class VerifyScreenAssertionRequest(BaseModel):
    """Payload for autonomous post-execution UI state assertion."""

    probe_id: str = Field(..., description="Unique assertion probe ID")
    expected_selector: str = Field(..., description="Selector expected to reflect state change")
    expected_text_contains: str = Field(..., description="Expected substring inside target element")
    actual_text: str = Field(..., description="Actual text scraped from element")
    visual_hash_match: bool = Field(default=True, description="Whether visual snapshot matches template")


class ScreenAssertionProbeResponse(BaseModel):
    """Result of autonomous UI assertion verification."""

    probe_id: str = Field(..., description="Probe ID")
    expected_selector: str = Field(..., description="Target selector")
    passed: bool = Field(..., description="Assertion pass/fail outcome")
    detail: str = Field(..., description="Diagnostic detail or failure description")


class BotScreenOperationalMetricsResponse(BaseModel):
    """Cumulative metrics tracking screen operations and human interventions."""

    total_screen_actions: int = Field(..., description="Total UI actions evaluated")
    approval_checkpoints_triggered: int = Field(..., description="High-risk actions paused for approval")
    manual_takeovers_conducted: int = Field(..., description="Critical actions requiring manual takeover")
    assertion_failures: int = Field(..., description="Autonomous screen assertion failures")
    evidence_bundles_sealed: int = Field(..., description="Total sealed tamper-proof audit bundles")
