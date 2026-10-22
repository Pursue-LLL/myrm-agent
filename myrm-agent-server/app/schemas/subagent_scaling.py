"""Pydantic V2 schemas for Subagent Concurrency & Tool Budget Adaptive Scaling (Item 31).

[INPUT]
- Raw subagent execution configuration and execution heartbeat metrics.

[OUTPUT]
- Migration audit DTOs, watermark heartbeat alerts, and active threshold status.

[POS]
- Provides typed data contracts for zero-disruption configuration migration
  and 80% dynamic watermark monitoring for subagent workloads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConfigScalar = str | int | float | bool | None


class SubagentConfigMigrationRequest(BaseModel):
    """Request payload to test or trigger zero-disruption configuration migration."""

    model_config = ConfigDict(frozen=True)

    concurrency_limit: int | None = Field(
        None,
        description="Configured concurrency limit (legacy default {3, 5} will be lifted)",
    )
    max_turns: int | None = Field(
        None,
        description="Configured tool turns budget (legacy default {25, 50} will be lifted)",
    )
    max_children_per_agent: int | None = Field(
        None,
        description="Direct child subagent limit per parent agent",
    )
    max_descendants_per_run: int | None = Field(
        None,
        description="Maximum total descendants per execution run",
    )
    extra_config: dict[str, ConfigScalar] = Field(
        default_factory=dict,
        description="Preserved extra metadata and configurations",
    )


class SubagentConfigMigrationResponse(BaseModel):
    """Audit report for zero-disruption configuration migration."""

    model_config = ConfigDict(frozen=True)

    migrated: bool
    old_concurrency: int | None
    new_concurrency: int
    old_max_turns: int | None
    new_max_turns: int
    concurrency_migrated: bool
    max_turns_migrated: bool
    reasons: list[str]
    final_config: dict[str, ConfigScalar]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class WatermarkHeartbeatRequest(BaseModel):
    """Execution turn heartbeat sent by or on behalf of an active subagent."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Associated parent session identifier")
    subagent_id: str = Field(..., min_length=1, description="Unique subagent task identifier")
    subagent_name: str = Field(default="Subagent", description="Human-readable subagent name")
    current_turn: int = Field(..., ge=0, description="Current completed turn count")
    max_turns: int = Field(..., gt=0, description="Total allocated max turns budget")
    threshold_ratio: float = Field(
        default=0.80,
        ge=0.1,
        le=0.99,
        description="Watermark threshold ratio (default 80%)",
    )


class WatermarkHeartbeatResponse(BaseModel):
    """Response containing watermark calculation and single-trigger warning status."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    subagent_id: str
    current_turn: int
    max_turns: int
    usage_ratio: float
    turns_remaining: int
    is_alert_triggered: bool
    alert_message: str | None = None


class WatermarkAlertItem(BaseModel):
    """Active or persisted watermark warning record for supervision HUD."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    subagent_id: str
    subagent_name: str
    current_turn: int
    max_turns: int
    usage_ratio: float
    turns_remaining: int
    status: Literal["active", "dismissed", "expanded"] = "active"
    warning_message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class WatermarkAlertListResponse(BaseModel):
    """Collection of watermark alerts across subagent tasks."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    alerts: list[WatermarkAlertItem]
    count: int
