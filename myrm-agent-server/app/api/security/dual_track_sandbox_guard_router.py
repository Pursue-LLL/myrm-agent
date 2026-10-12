"""API router for Dual-Track Soft Memory vs Hard Redline Sandbox Guard.

[INPUT]
- EvaluateExecutionRequest, RegisterRedlineRuleRequest payloads.

[OUTPUT]
- ExecutionInterceptionDto, HardRedlineRuleDto, CompiledPolicySummaryDto responses.

[POS]
- Security router mounted under /security/dual-track-sandbox-guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.dual_track_sandbox_guard import (
    CompiledPolicySummaryDto,
    EvaluateExecutionRequest,
    ExecutionInterceptionDto,
    HardRedlineRuleDto,
    RegisterRedlineRuleRequest,
)
from app.services.security.dual_track_sandbox_guard_service import (
    DualTrackSandboxGuardService,
    get_dual_track_sandbox_guard_service,
)

router = APIRouter(
    prefix="/dual-track-sandbox-guard", tags=["dual-track-sandbox-guard"]
)


@router.post("/evaluate-execution", response_model=ExecutionInterceptionDto)
async def evaluate_execution(
    request: EvaluateExecutionRequest,
    service: DualTrackSandboxGuardService = Depends(
        get_dual_track_sandbox_guard_service
    ),
) -> ExecutionInterceptionDto:
    """Evaluate file access or shell command against the compiled physical sandbox execution firewall."""
    return service.evaluate_execution(request)


@router.post("/register-rule", response_model=HardRedlineRuleDto)
async def register_rule(
    request: RegisterRedlineRuleRequest,
    service: DualTrackSandboxGuardService = Depends(
        get_dual_track_sandbox_guard_service
    ),
) -> HardRedlineRuleDto:
    """Register custom hard redline rule into sandbox policy compiler."""
    return service.register_rule(request)


@router.get("/compiled-policy", response_model=CompiledPolicySummaryDto)
async def get_compiled_policy(
    service: DualTrackSandboxGuardService = Depends(
        get_dual_track_sandbox_guard_service
    ),
) -> CompiledPolicySummaryDto:
    """Inspect active compiled sandbox physical firewall rules."""
    return service.get_compiled_policy()


@router.get("/rules", response_model=list[HardRedlineRuleDto])
async def list_rules(
    service: DualTrackSandboxGuardService = Depends(
        get_dual_track_sandbox_guard_service
    ),
) -> list[HardRedlineRuleDto]:
    """List all configured hard redline rules."""
    return service.list_rules()
