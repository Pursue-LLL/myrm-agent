"""Pydantic schemas for Computer-Use Safe Enclave and Action Replay Audit Deck.

[INPUT]
None.

[OUTPUT]
DTO models for desktop action evaluation, interception challenges, emergency panic,
and live intent HUD feeds.

[POS]
Server schemas. Exposes typed contracts for safe computer-use execution.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class DesktopActionDto(BaseModel):
    """Payload representing a candidate OS-level desktop action."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(..., description="Unique action identifier")
    action_type: str = Field(..., description="Action type (mouse_click, key_press, etc.)")
    semantic_intent: str = Field(..., description="Semantic purpose or intent of the action")
    coordinates: tuple[int, int] | None = Field(default=None, description="Screen (X, Y) coordinates")
    target_element_text: str | None = Field(default=None, description="Text label of target UI element")
    payload_text: str | None = Field(default=None, description="Text payload or key combination")
    risk_level: str = Field(default="safe", description="Risk tier: safe, suspicious, critical")
    timestamp: float = Field(default_factory=time.time, description="Action timestamp")


class ActionEnclaveChallengeDto(BaseModel):
    """Enclave challenge requiring explicit human sign-off."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(..., description="Challenge unique ID")
    action: DesktopActionDto = Field(..., description="Intercepted action")
    reason: str = Field(..., description="Security reason for interception")
    status: str = Field(..., description="Status: pending, approved, rejected, panicked")
    created_at: float = Field(..., description="Timestamp when challenge was created")


class EvaluateActionRequest(BaseModel):
    """Payload to evaluate an impending desktop action."""

    model_config = ConfigDict(extra="forbid")

    action: DesktopActionDto = Field(..., description="Candidate action to evaluate")


class EvaluateActionResponse(BaseModel):
    """Result of desktop action safety evaluation."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(..., description="Whether action can proceed immediately")
    challenge: ActionEnclaveChallengeDto | None = Field(default=None, description="Challenge if intercepted")
    reason: str = Field(..., description="Evaluation summary or policy decision reason")


class ChallengeDecisionRequest(BaseModel):
    """Human decision payload on an intercepted desktop action challenge."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(..., description="Target challenge identifier")
    approved: bool = Field(..., description="Whether the action is approved to execute")
    reason: str = Field(default="", description="Optional human note or justification")


class ChallengeDecisionResponse(BaseModel):
    """Outcome of human challenge decision."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(..., description="Target challenge identifier")
    status: str = Field(..., description="New challenge status: approved or rejected")
    action: DesktopActionDto | None = Field(default=None, description="Approved action if authorized")
    message: str = Field(..., description="Status message")


class PanicTriggerRequest(BaseModel):
    """Payload to activate the emergency panic killswitch."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="User emergency panic stop activated", description="Panic reason")


class PanicStatusResponse(BaseModel):
    """Current state of emergency panic circuit breaker."""

    model_config = ConfigDict(extra="forbid")

    is_panicked: bool = Field(..., description="True if emergency stop is engaged")
    panic_reason: str = Field(..., description="Reason for active emergency stop")


class LiveIntentFeedItem(BaseModel):
    """Single telemetry record for Live Intent HUD."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(..., description="Telemetry record ID")
    action_id: str = Field(..., description="Action ID")
    action_type: str = Field(..., description="Action type")
    semantic_intent: str = Field(..., description="Semantic intent")
    risk_level: str = Field(..., description="Assessed risk tier")
    enclave_verified: bool = Field(..., description="Enclave sign-off status")
    executed: bool = Field(..., description="Whether action finished execution")
    status: str = Field(..., description="Audit status code")
    execution_latency_ms: float = Field(..., description="Execution latency in milliseconds")
    recorded_at: float = Field(..., description="Unix epoch timestamp")


class LiveIntentFeedResponse(BaseModel):
    """Live Intent HUD telemetry projection."""

    model_config = ConfigDict(extra="forbid")

    feed: list[LiveIntentFeedItem] = Field(default_factory=list, description="Telemetry items")
    count: int = Field(..., description="Total items returned")
