"""Model Overrides & BYOK Pricing API Router.

[INPUT]
- services.models.overrides::model_overrides_registry
- services.models.overrides.model_overrides_types::ModelOverrideItem, ModelOverrideUpsertRequest, PreloadedModelSku, CostEstimationRequest, CostEstimationResponse
- fastapi: APIRouter, HTTPException

[OUTPUT]
- model_overrides_router: FastAPI APIRouter 暴露模型覆写与 BYOK 成本计算端点

[POS]
API 层路由。为前端提供模型上下文窗口（Context Window）覆写、最大输出 Tokens 自定义、
输入输出单价覆写与 BYOK 实时成本估算能力。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from app.services.models.overrides.model_overrides_registry import (
    model_overrides_registry,
)
from app.services.models.overrides.model_overrides_types import (
    CostEstimationRequest,
    CostEstimationResponse,
    ModelOverrideItem,
    ModelOverrideUpsertRequest,
    PreloadedModelSku,
)

logger = logging.getLogger(__name__)

model_overrides_router = APIRouter()


@model_overrides_router.get("", response_model=list[ModelOverrideItem])
async def list_model_overrides() -> list[ModelOverrideItem]:
    """List all registered custom model override configurations."""
    return model_overrides_registry.list_overrides()


@model_overrides_router.get("/preloaded/skus", response_model=list[PreloadedModelSku])
async def list_preloaded_skus() -> list[PreloadedModelSku]:
    """Retrieve preloaded modern 2026 baseline model SKU templates."""
    return model_overrides_registry.get_preloaded_skus()


@model_overrides_router.get("/{model_id}", response_model=ModelOverrideItem)
async def get_model_override(model_id: str) -> ModelOverrideItem:
    """Retrieve custom override settings for a specific model."""
    override = model_overrides_registry.get_override(model_id)
    if override is None:
        raise HTTPException(
            status_code=404,
            detail=f"No custom override configured for model '{model_id}'.",
        )
    return override


@model_overrides_router.put("/{model_id}", response_model=ModelOverrideItem)
async def upsert_model_override(
    model_id: str,
    payload: ModelOverrideUpsertRequest,
) -> ModelOverrideItem:
    """Create or update custom context window and pricing override for a model."""
    item = ModelOverrideItem(
        model_id=model_id,
        custom_context_window=payload.custom_context_window,
        custom_max_output_tokens=payload.custom_max_output_tokens,
        input_cost_per_mtoken=payload.input_cost_per_mtoken,
        output_cost_per_mtoken=payload.output_cost_per_mtoken,
        currency=payload.currency,
        enabled=payload.enabled,
        remarks=payload.remarks,
    )
    return model_overrides_registry.upsert_override(item)


@model_overrides_router.delete("/{model_id}")
async def delete_model_override(model_id: str) -> dict[str, str]:
    """Delete an existing model override and reset model parameters to default."""
    deleted = model_overrides_registry.delete_override(model_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No custom override found for model '{model_id}' to delete.",
        )
    return {"message": f"Override for model '{model_id}' successfully removed."}


@model_overrides_router.post("/estimate-cost", response_model=CostEstimationResponse)
async def estimate_byok_cost(
    request: CostEstimationRequest,
) -> CostEstimationResponse:
    """Calculate projected token economics using effective pricing matrices."""
    return model_overrides_registry.estimate_cost(request)
