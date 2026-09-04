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


class ValidateExternalSecretRequest(BaseModel):
    reference: str = Field(..., description="External secret reference (op:// or bw://)")


@router.post("/validate-secret-reference")
async def validate_external_secret_reference(body: ValidateExternalSecretRequest) -> dict[str, object]:
    """Test resolution of an external secret URI (1Password / Bitwarden) in memory."""
    from myrm_agent_harness.api import (
        ExternalSecretResolutionError,
        is_external_secret_reference,
        resolve_external_secret,
    )

    ref = body.reference.strip()
    if not is_external_secret_reference(ref):
        return success_response({
            "valid": False,
            "error": "Not a recognized external secret URI scheme (expected op:// or bw://)",
        })

    try:
        resolved = resolve_external_secret(ref)
        masked = f"{resolved[:3]}...{resolved[-3:]}" if len(resolved) > 6 else "***"
        return success_response({
            "valid": True,
            "masked_preview": masked,
            "error": None,
        })
    except ExternalSecretResolutionError as e:
        return success_response({
            "valid": False,
            "error": str(e),
        })


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
