"""Model Overrides & Context Pricing Data Contracts.

[INPUT]
- pydantic: BaseModel, Field
- enum: Enum

[OUTPUT]
- Currency: Enum representing supported currency types (USD, CNY)
- ModelOverrideItem: Model representing customizable context window and token pricing overrides
- ModelOverrideUpsertRequest: Request schema to save model override
- PreloadedModelSku: Schema representing modern 2026 pre-calibrated model templates
- CostEstimationRequest: Schema for BYOK cost calculator calculation request
- CostEstimationResponse: Schema reporting projected input, output, and total token costs

[POS]
Data contracts for model_overrides mechanism (Hermes Agent v0.21.0 parity).
Allows users to independently override context window sizes and pricing matrices
without waiting for official platform release cadences.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Currency(str, Enum):
    """Supported currency denomination."""

    USD = "USD"
    CNY = "CNY"


class ModelOverrideItem(BaseModel):
    """Individual model override configuration entry."""

    model_id: str = Field(..., min_length=1, description="Model identifier or alias (e.g. glm-5.3-flash, qwen-3.8-max)")
    custom_context_window: int | None = Field(
        default=None,
        ge=1024,
        le=10_000_000,
        description="Custom context window size in tokens",
    )
    custom_max_output_tokens: int | None = Field(
        default=None,
        ge=512,
        le=131_072,
        description="Custom maximum output tokens limit",
    )
    input_cost_per_mtoken: float | None = Field(
        default=None,
        ge=0.0,
        description="Custom input token price per 1 million tokens",
    )
    output_cost_per_mtoken: float | None = Field(
        default=None,
        ge=0.0,
        description="Custom output token price per 1 million tokens",
    )
    currency: Currency = Field(
        default=Currency.USD,
        description="Pricing currency (USD or CNY)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this override entry is actively applied",
    )
    remarks: str | None = Field(
        default=None,
        description="Optional user notes, e.g. OneAPI / NewAPI proxy endpoint note",
    )


class ModelOverrideUpsertRequest(BaseModel):
    """Payload to create or update a model override."""

    custom_context_window: int | None = Field(
        default=None,
        ge=1024,
        le=10_000_000,
        description="Custom context window size in tokens",
    )
    custom_max_output_tokens: int | None = Field(
        default=None,
        ge=512,
        le=131_072,
        description="Custom maximum output tokens limit",
    )
    input_cost_per_mtoken: float | None = Field(
        default=None,
        ge=0.0,
        description="Custom input token price per 1 million tokens",
    )
    output_cost_per_mtoken: float | None = Field(
        default=None,
        ge=0.0,
        description="Custom output token price per 1 million tokens",
    )
    currency: Currency = Field(
        default=Currency.USD,
        description="Pricing currency (USD or CNY)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this override entry is actively applied",
    )
    remarks: str | None = Field(
        default=None,
        description="Optional user notes",
    )


class PreloadedModelSku(BaseModel):
    """Modern 2026 pre-calibrated baseline model SKU for quick cloning."""

    model_id: str = Field(..., description="Canonical model identifier")
    display_name: str = Field(..., description="Human-friendly model title")
    provider: str = Field(..., description="Upstream provider or lab")
    default_context_window: int = Field(..., description="Default baseline context window in tokens")
    default_max_output_tokens: int = Field(..., description="Default baseline output tokens limit")
    suggested_input_cost_per_mtoken: float = Field(..., description="Reference input price per 1M tokens")
    suggested_output_cost_per_mtoken: float = Field(..., description="Reference output price per 1M tokens")
    currency: Currency = Field(default=Currency.USD, description="Reference currency")
    recommended_use_case: str = Field(..., description="Brief guidance on suitable tasks")


class CostEstimationRequest(BaseModel):
    """Payload for BYOK real-time cost calculator."""

    model_id: str = Field(..., description="Target model identifier")
    input_tokens: int = Field(default=10_000, ge=0, description="Estimated prompt input tokens")
    output_tokens: int = Field(default=2_000, ge=0, description="Estimated completion output tokens")


class CostEstimationResponse(BaseModel):
    """Detailed projected cost calculation result."""

    model_id: str = Field(..., description="Target model identifier")
    input_tokens: int = Field(..., description="Calculated input tokens")
    output_tokens: int = Field(..., description="Calculated output tokens")
    input_cost: float = Field(..., description="Total input cost")
    output_cost: float = Field(..., description="Total output cost")
    total_cost: float = Field(..., description="Sum of input and output costs")
    currency: Currency = Field(..., description="Currency symbol/code")
    is_overridden: bool = Field(..., description="Whether price was derived from user custom override")
