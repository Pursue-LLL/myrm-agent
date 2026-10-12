"""API router for LLM Egress Default-Deny & Credential Binding.

[INPUT]
- EvaluateLlmEgressRequest, SetLlmEgressPolicyRequest payloads.

[OUTPUT]
- LlmEgressVerdictDto, LlmEgressPolicyDto responses.

[POS]
- Security router mounted under /security/llm-egress-guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.llm_egress_guard import (
    EvaluateLlmEgressRequest,
    LlmEgressPolicyDto,
    LlmEgressVerdictDto,
    SetLlmEgressPolicyRequest,
)
from app.services.security.llm_egress_guard_service import (
    LlmEgressGuardService,
    get_llm_egress_guard_service,
)

router = APIRouter(prefix="/llm-egress-guard", tags=["llm-egress-guard"])


@router.post("/evaluate", response_model=LlmEgressVerdictDto)
async def evaluate_llm_egress(
    request: EvaluateLlmEgressRequest,
    service: LlmEgressGuardService = Depends(get_llm_egress_guard_service),
) -> LlmEgressVerdictDto:
    """Evaluate an outbound destination and credential against active egress policy."""
    return service.evaluate_egress(request)


@router.post("/policy", response_model=LlmEgressPolicyDto)
async def set_llm_egress_policy(
    request: SetLlmEgressPolicyRequest,
    service: LlmEgressGuardService = Depends(get_llm_egress_guard_service),
) -> LlmEgressPolicyDto:
    """Install or update the active default-deny LLM egress policy."""
    return service.set_policy(request)


@router.get("/policy", response_model=LlmEgressPolicyDto)
async def get_llm_egress_policy(
    service: LlmEgressGuardService = Depends(get_llm_egress_guard_service),
) -> LlmEgressPolicyDto:
    """Retrieve current active LLM egress policy."""
    policy = service.get_policy()
    if policy is None:
        raise HTTPException(
            status_code=404,
            detail="No active LLM egress policy installed (currently fail-closed).",
        )
    return policy


@router.delete("/policy")
async def clear_llm_egress_policy(
    service: LlmEgressGuardService = Depends(get_llm_egress_guard_service),
) -> dict[str, str | bool]:
    """Clear active egress policy, immediately returning guard to fail-closed state."""
    service.clear_policy()
    return {"success": True, "message": "Policy cleared; egress is now fail-closed."}
