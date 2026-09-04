"""Credential Pool observability and management endpoints.

[INPUT]
- myrm_agent_harness.toolkits.llms.core.manager::LLMManager

[OUTPUT]
- GET /stats: Return aggregated statistics for active credential pools across cached LLM instances.
- POST /reset-cooldowns: Reset cooldown states and rate-limit counters for all or specific key slots.

[POS]
Integrations API sub-router providing runtime observability and control
over multi-key rotation and cooldowns in CredentialPool.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from myrm_agent_harness.toolkits.llms.core.manager import LLMManager
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response

logger = logging.getLogger(__name__)

router = APIRouter()


class ResetCooldownsRequest(BaseModel):
    key_suffix: str | None = Field(default=None, description="Optional key suffix to target specific slots")


@router.get("/stats")
async def get_credential_pool_stats() -> dict[str, object]:
    """Get active credential pool observability statistics across all cached models."""
    pools = LLMManager.get_pool_stats()
    return success_response(pools)


@router.post("/reset-cooldowns")
async def reset_credential_pool_cooldowns(body: ResetCooldownsRequest | None = None) -> dict[str, object]:
    """Reset cooldown timers and consecutive rate limit counters for matching keys."""
    key_suffix = body.key_suffix if body else None
    reset_count = LLMManager.reset_pool_cooldowns(key_suffix=key_suffix)
    return success_response({"reset_count": reset_count})
