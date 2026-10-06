"""Pydantic schemas for Autonomous Bot Budget Guardrail and Token Ceiling Circuit Breaker.

[INPUT]
- None (Self-contained schema representations for bot quota and spend tracking)

[OUTPUT]
- RegisterBotQuotaRequest, BotQuotaResponse, RecordUsageRequest, CircuitBreakerStatusResponse

[POS]
- app.schemas.bot_budget_guardrail
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegisterBotQuotaRequest(BaseModel):
    """Payload to register or update an autonomous bot budget sandbox."""

    model_config = ConfigDict(extra="forbid")

    bot_id: str = Field(..., min_length=1, max_length=64, description="Unique bot or channel identifier")
    bot_name: str = Field(..., min_length=1, max_length=128, description="Display name of the bot")
    sandbox_mode: str = Field(
        default="ISOLATED_SANDBOX",
        description="Budget isolation mode: ISOLATED_SANDBOX or CORE_PROTECTED",
    )
    token_ceiling: int = Field(..., ge=1, description="Hard ceiling for total allowed tokens")
    cost_ceiling_usd: float = Field(..., gt=0.0, description="Hard ceiling for total dollar spend in USD")
    warning_threshold: float = Field(
        default=0.8,
        ge=0.1,
        le=0.99,
        description="Ratio (e.g. 0.8) at which soft warning is tripped",
    )


class BotQuotaResponse(BaseModel):
    """Status details for an autonomous bot budget sandbox."""

    model_config = ConfigDict(extra="forbid")

    bot_id: str
    bot_name: str
    sandbox_mode: str
    token_ceiling: int
    cost_ceiling_usd: float
    used_tokens: int
    used_cost_usd: float
    warning_threshold: float
    state: str
    frozen_at: float | None
    last_updated_at: float


class ConsumeBudgetRequest(BaseModel):
    """Request to evaluate and deduct execution tokens and cost."""

    model_config = ConfigDict(extra="forbid")

    bot_id: str = Field(..., min_length=1, max_length=64, description="Bot identifier")
    tokens: int = Field(..., ge=0, description="Tokens consumed or projected")
    cost_usd: float = Field(..., ge=0.0, description="Estimated or actual cost in USD")


class ConsumeBudgetResponse(BaseModel):
    """Outcome of token and cost consumption check."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(..., description="Whether execution is permitted under current ceilings")
    bot_id: str
    state: str = Field(..., description="Circuit breaker state: CLOSED, HALF_OPEN, or OPEN_FROZEN")
    current_used_tokens: int
    current_used_cost_usd: float
    tokens_remaining: int
    cost_remaining_usd: float
    rejection_reason: str | None = None


class RefuelBotQuotaRequest(BaseModel):
    """Request to increase quota ceilings and reset tripped circuit breaker."""

    model_config = ConfigDict(extra="forbid")

    bot_id: str = Field(..., min_length=1, max_length=64, description="Bot identifier to refuel")
    additional_tokens: int = Field(default=0, ge=0, description="Additional tokens to add to ceiling")
    additional_cost_usd: float = Field(default=0.0, ge=0.0, description="Additional USD budget to add to ceiling")
    reset_state: bool = Field(default=True, description="Whether to unfreeze and restore circuit breaker state")


class BotQuotaListResponse(BaseModel):
    """Collection of configured bot budget sandboxes."""

    model_config = ConfigDict(extra="forbid")

    quotas: list[BotQuotaResponse]
    total: int
