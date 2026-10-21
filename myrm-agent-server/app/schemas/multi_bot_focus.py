"""Pydantic V2 schemas for Multi-Bot Mention Focus & Anti-Thrash Compaction (Item 42).

[INPUT]
- UpdateBotFocusRequest, EvaluateCompactionRequest, RecordCompactionRequest,
  CardHeartbeatRequest, PruneAbandonedStreamsRequest.

[OUTPUT]
- Strongly-typed DTOs for viewport bot focus tracking, anti-thrash compaction decisions,
  and dead stream task card pruning.

[POS]
- Server-side typed schemas for multi-bot focus and compaction APIs.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class StreamCardStateEnum(enum.StrEnum):
    """Lifecycle state of a streaming multi-bot task progress card."""

    STREAMING = "streaming"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    FAILED = "failed"


class BotFocusSnapshotDTO(BaseModel):
    """Snapshot representing the focus score and viewport activity of a bot."""

    model_config = ConfigDict(frozen=True)

    bot_id: str = Field(..., min_length=1, description="Bot identifier")
    is_viewport_active: bool = Field(..., description="Whether bot is visible in viewport")
    last_active_turn: int = Field(..., ge=0, description="Last turn index of activity")
    focus_score: float = Field(..., description="Calculated dynamic focus score")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Snapshot timestamp"
    )


class CompactionPolicyDTO(BaseModel):
    """Hysteresis and cooldown configuration for anti-thrash compaction."""

    model_config = ConfigDict(frozen=True)

    trigger_threshold_ratio: float = Field(
        default=0.90, ge=0.5, le=1.0, description="Context window ratio to trigger compaction"
    )
    target_threshold_ratio: float = Field(
        default=0.75, ge=0.3, le=0.9, description="Target context ratio after compaction"
    )
    cooldown_turns: int = Field(
        default=3, ge=1, le=50, description="Cooldown turns between successive compactions"
    )
    min_token_delta: int = Field(
        default=500, ge=0, description="Minimum token growth required to re-trigger"
    )


class CompactionEvaluationDTO(BaseModel):
    """Result of an anti-thrash compaction check preventing high-frequency churn."""

    model_config = ConfigDict(frozen=True)

    should_compact: bool = Field(..., description="Whether compaction is recommended")
    reason: str = Field(..., description="Human-readable decision explanation")
    current_tokens: int = Field(..., ge=0, description="Current context token usage")
    max_context_tokens: int = Field(..., gt=0, description="Maximum context window ceiling")
    cooldown_remaining: int = Field(
        default=0, ge=0, description="Remaining turns in cooldown window"
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Evaluation timestamp"
    )


class StreamCardHeartbeatDTO(BaseModel):
    """Heartbeat telemetry for streaming multi-bot task cards preventing zombie states."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(..., min_length=1, description="Unique task card ID")
    session_id: str = Field(..., min_length=1, description="Origin session identifier")
    bot_id: str = Field(..., min_length=1, description="Bot owning the streaming card")
    state: StreamCardStateEnum = Field(
        default=StreamCardStateEnum.STREAMING, description="Card lifecycle state"
    )
    last_heartbeat_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Last heartbeat timestamp"
    )


class UpdateBotFocusRequest(BaseModel):
    """Request to update viewport visibility and active turn for a bot."""

    model_config = ConfigDict(frozen=True)

    bot_id: str = Field(..., min_length=1, description="Target bot ID")
    is_viewport_active: bool = Field(..., description="Whether bot is in visible viewport")
    turn_index: int = Field(default=0, ge=0, description="Current chat turn index")


class FocusedBotResponse(BaseModel):
    """Response indicating the current highest-priority focused bot for @mention."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Chat session ID")
    focused_bot_id: str | None = Field(default=None, description="Recommended mention target")
    snapshots: list[BotFocusSnapshotDTO] = Field(
        default_factory=list, description="All tracked bot snapshots in session"
    )


class EvaluateCompactionRequest(BaseModel):
    """Request to evaluate context window compaction with anti-thrash guards."""

    model_config = ConfigDict(frozen=True)

    current_tokens: int = Field(..., ge=0, description="Current token usage count")
    max_context_tokens: int = Field(..., gt=0, description="Max token window ceiling")
    current_turn: int = Field(..., ge=0, description="Current turn counter")
    policy: CompactionPolicyDTO | None = Field(
        default=None, description="Optional custom policy override"
    )


class RecordCompactionRequest(BaseModel):
    """Request to record completion of a compaction turn to reset cooldown timer."""

    model_config = ConfigDict(frozen=True)

    executed_turn: int = Field(..., ge=0, description="Turn index where compaction finished")
    tokens_after: int = Field(..., ge=0, description="Token usage count after compaction")


class CardHeartbeatRequest(BaseModel):
    """Request to emit or refresh heartbeat for an active task progress card."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(..., min_length=1, description="Unique task card ID")
    bot_id: str = Field(..., min_length=1, description="Bot ID generating output")
    state: StreamCardStateEnum = Field(
        default=StreamCardStateEnum.STREAMING, description="Current state"
    )


class PruneAbandonedStreamsRequest(BaseModel):
    """Request to scan and mark expired streaming cards as abandoned."""

    model_config = ConfigDict(frozen=True)

    timeout_seconds: float = Field(
        default=30.0, ge=1.0, le=3600.0, description="Inactivity timeout in seconds"
    )
