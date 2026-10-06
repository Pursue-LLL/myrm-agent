"""
[POS] app/schemas/memory_dialectic.py
[INPUT] pydantic
[OUTPUT] UserBaseProfileDTO, DialecticEphemeralMindDTO, DialecticCadenceConfigDTO, DialecticProcessTurnRequestDTO, DialecticReasoningResponseDTO, DialecticCadenceStatusResponseDTO

Pydantic DTOs for Dialectic Profile Reasoning and Adaptive Context Cadence Engine.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserBaseProfileDTO(BaseModel):
    """Long-term relatively static user identity and architectural style profile."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="Target user ID")
    primary_role: str = Field(default="", description="User primary role or specialty")
    technical_stack: list[str] = Field(
        default_factory=list, description="Mastered technical stack competencies"
    )
    preferred_style: str = Field(
        default="", description="Architectural conventions and design preferences"
    )
    core_constraints: list[str] = Field(
        default_factory=list, description="Hard non-negotiable architectural constraints"
    )
    last_updated_at: str = Field(..., description="ISO 8601 timestamp of last profile update")


class DialecticEphemeralMindDTO(BaseModel):
    """Dynamic ephemeral cognition layer capturing immediate concerns and friction points."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Target conversation ID")
    immediate_focus: str = Field(..., description="Immediate focus in current interaction turn")
    resistance_points: list[str] = Field(
        default_factory=list, description="User resistance points or explicit aversions"
    )
    implicit_goals: list[str] = Field(
        default_factory=list, description="Latent subconscious user goals"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")
    turn_index: int = Field(default=0, ge=0, description="Conversation turn index")
    updated_at: str = Field(..., description="ISO 8601 update timestamp")


class DialecticCadenceConfigDTO(BaseModel):
    """Configuration tuning the adaptive context cadence and throttling scheduler."""

    model_config = ConfigDict(extra="forbid")

    base_profile_cadence_turns: int = Field(
        default=5, gt=0, description="Cadence interval in turns for base profile review"
    )
    ephemeral_cadence_turns: int = Field(
        default=2, gt=0, description="Cadence interval in turns for ephemeral mind extraction"
    )
    cold_boot_threshold_turns: int = Field(
        default=2, ge=0, description="Threshold turns defining cold-boot phase"
    )
    max_ephemeral_chars: int = Field(
        default=500, gt=0, description="Maximum characters allowed in volatile prompt slice"
    )
    enable_throttling: bool = Field(
        default=True, description="True to enforce dynamic cadence rate throttling"
    )


class DialecticProcessTurnRequestDTO(BaseModel):
    """Request payload to process an interaction turn through dialectic reasoning."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Target conversation ID")
    user_prompt: str = Field(..., description="Current user prompt text")
    assistant_response: str = Field(
        default="", description="Optional assistant response text"
    )
    turn_index: int | None = Field(
        default=None, ge=0, description="Explicit turn index override"
    )


class DialecticReasoningResponseDTO(BaseModel):
    """Response capturing dialectic reasoning conclusions and prompt slices."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Target conversation ID")
    turn_index: int = Field(..., ge=0, description="Current turn index")
    is_throttled: bool = Field(..., description="True if dialectic extraction was throttled")
    heat_state: str = Field(..., description="Current session heat state: cold_boot, warm, hot_active")
    base_profile_updated: bool = Field(
        ..., description="True if base profile underwent evaluation this turn"
    )
    ephemeral_mind_updated: bool = Field(
        ..., description="True if ephemeral mind was extracted this turn"
    )
    ephemeral_mind: DialecticEphemeralMindDTO | None = Field(
        default=None, description="Active or newly extracted ephemeral mind snapshot"
    )
    prompt_volatile_slice: str = Field(
        default="", description="Rendered volatile prompt slice for prefix cache safety"
    )
    reasoning_summary: str = Field(..., description="Operational summary of the dialectic run")


class DialecticCadenceStatusResponseDTO(BaseModel):
    """Telemetry report describing live cadence governor status for a session."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Target conversation ID")
    current_turn: int = Field(..., ge=0, description="Current conversation turn index")
    heat_state: str = Field(..., description="Session heat classification")
    should_extract_ephemeral: bool = Field(
        ..., description="True if next turn will trigger ephemeral mind extraction"
    )
    should_refresh_base_profile: bool = Field(
        ..., description="True if next turn will trigger base profile review"
    )
