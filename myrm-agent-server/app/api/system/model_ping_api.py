"""FastAPI endpoint for instant model connectivity and latency probing.

[INPUT]
- ModelPingRequest DTO
- app.services.system.model_ping_service

[OUTPUT]
- router: APIRouter instance exposing POST /system/model-ping

[POS]
app/api/system/model_ping_api.py: 提供模型即时测速验证接口，供设置页与模型选择器即时探活。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.services.system.model_ping_service import (
    ModelPingResult,
    ModelPingService,
    get_model_ping_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System Diagnostics"])


class ModelPingRequest(BaseModel):
    model_id: str = Field(..., min_length=1, description="Target model identifier to test")
    provider: str = Field(default="openai", description="Model provider key (e.g. anthropic, openrouter, ollama)")
    timeout_seconds: float = Field(default=8.0, ge=1.0, le=30.0, description="Probe timeout in seconds")


@router.post(
    "/model-ping",
    response_model=ModelPingResult,
    status_code=status.HTTP_200_OK,
    summary="Ping a model configuration for instant latency and throughput validation",
)
async def ping_model_endpoint(
    req: ModelPingRequest,
    service: ModelPingService = Depends(get_model_ping_service),
) -> ModelPingResult:
    """Test model connection, measuring TTFT, tokens/sec, and credentials validity."""
    return await service.ping_model(
        model_id=req.model_id,
        provider=req.provider,
        timeout_seconds=req.timeout_seconds,
    )
