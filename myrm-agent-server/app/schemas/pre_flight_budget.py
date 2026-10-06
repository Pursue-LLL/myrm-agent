"""Pydantic schemas for Live Pre-Flight Budget Chokepoint Suite.

[INPUT]
None (Pydantic schema definitions).

[OUTPUT]
BudgetActionEnum: Budget action types (pause/stop).
BudgetPeriodEnum: Budget calculation windows (daily/session/total).
BudgetConfigCreateRequest, BudgetConfigResponse: Configuration DTOs.
RecordSpendRequest, SpendRecordResponse: Spend recording DTOs.
EvaluateBudgetRequest, BudgetDecisionResponse: Pre-flight evaluation DTOs.
BudgetBroadcastEventResponse, QueueAllowedResponse: Event and queue response DTOs.

[POS]
运行前预算卡点安全模式定义层。为项目级 LLM 调用实时预算监控、卡点阻断与事件总线广播提供强类型数据模型。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class BudgetActionEnum(StrEnum):
    """Normalized budget enforcement action."""

    PAUSE = "pause"
    STOP = "stop"


class BudgetPeriodEnum(StrEnum):
    """Budget calculation time window."""

    DAILY = "daily"
    SESSION = "session"
    TOTAL = "total"


class BudgetConfigCreateRequest(BaseModel):
    """Request payload to set or update project budget."""

    project_id: str = Field(..., description="Project unique identifier")
    limit_amount: float = Field(..., gt=0.0, description="Budget limit amount")
    currency: str = Field(default="USD", description="Currency ISO code")
    period: BudgetPeriodEnum = Field(
        default=BudgetPeriodEnum.DAILY, description="Calculation window"
    )
    action: BudgetActionEnum = Field(
        default=BudgetActionEnum.PAUSE, description="Action when breached"
    )
    anchor_timestamp: float | None = Field(
        default=None, description="Anchor lower bound timestamp for window"
    )


class BudgetConfigResponse(BaseModel):
    """Response containing live project budget configuration."""

    project_id: str
    limit_amount: float
    currency: str
    period: BudgetPeriodEnum
    action: BudgetActionEnum
    anchor_timestamp: float | None


class RecordSpendRequest(BaseModel):
    """Request payload to record an LLM call spend."""

    project_id: str = Field(..., description="Project unique identifier")
    amount: float = Field(..., gt=0.0, description="Cost amount spent")
    currency: str = Field(default="USD", description="Currency code")
    model_name: str = Field(default="default-model", description="Model invoked")
    source: str = Field(default="management", description="Spend source category")


class SpendRecordResponse(BaseModel):
    """Response containing a recorded spend item."""

    project_id: str
    amount: float
    currency: str
    model_name: str
    source: str
    timestamp: float


class EvaluateBudgetRequest(BaseModel):
    """Request payload to evaluate budget status."""

    project_id: str = Field(..., description="Project unique identifier")


class BudgetDecisionResponse(BaseModel):
    """Response representing live single enforcement point decision."""

    tripped: bool
    action: BudgetActionEnum
    project_id: str
    current_spend: float
    limit: float
    currency: str
    period: BudgetPeriodEnum
    reason: str | None


class QueueAllowedResponse(BaseModel):
    """Response representing queue dispatch lock status."""

    project_id: str
    queue_dispatch_allowed: bool
    reason: str


class BudgetBroadcastEventResponse(BaseModel):
    """Response representing a broadcast event item."""

    event_type: str
    project_id: str
    timestamp: float
    payload: dict[str, str | float | bool]
