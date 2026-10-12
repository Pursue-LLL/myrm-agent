"""FastAPI router for PreToolUse Hook Interceptor & API Key Precedence.

[INPUT]
- JSON payloads inspecting proposed tool invocations and checking billing conflicts.

[OUTPUT]
- Serialized verdicts, hard gate security rejections, and billing conflict warnings.

[POS]
- REST API layer providing deterministic pre-tool dispatch gates and billing protection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.core.security.pre_tool_use_interceptor import (
    HardGateSecurityRejectionError,
)

from app.schemas.pre_tool_use_interceptor import (
    DetectApiKeyConflictRequest,
    DetectApiKeyConflictResponse,
    HardRuleSpecDto,
    InterceptToolUseRequest,
    InterceptToolUseResponse,
    ToggleRuleRequest,
)
from app.services.security.pre_tool_use_interceptor_service import (
    PreToolUseInterceptorService,
    get_pre_tool_use_interceptor_service,
)

router = APIRouter(
    prefix="/pre-tool-use-interceptor",
    tags=["Security: PreToolUse Interceptor"],
)


@router.post(
    "/intercept",
    response_model=InterceptToolUseResponse,
    summary="Inspect tool invocation against deterministic hard rules before dispatch",
)
def intercept_tool(
    request: InterceptToolUseRequest,
    service: PreToolUseInterceptorService = Depends(
        get_pre_tool_use_interceptor_service
    ),
) -> InterceptToolUseResponse:
    """Pre-execution inspection preventing command or file execution that breaches hard invariants."""
    try:
        return service.intercept_tool(request)
    except HardGateSecurityRejectionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err


@router.post(
    "/detect-key-conflict",
    response_model=DetectApiKeyConflictResponse,
    summary="Detect ambient environment variables that could cause silent billing surcharges",
)
def detect_key_conflict(
    request: DetectApiKeyConflictRequest,
    service: PreToolUseInterceptorService = Depends(
        get_pre_tool_use_interceptor_service
    ),
) -> DetectApiKeyConflictResponse:
    """Scan process environment to ensure ambient API keys do not silently override subscription routes."""
    return service.detect_key_conflicts(request)


@router.get(
    "/rules",
    response_model=list[HardRuleSpecDto],
    summary="Get catalog of active hard invariant rules",
)
def get_rules(
    service: PreToolUseInterceptorService = Depends(
        get_pre_tool_use_interceptor_service
    ),
) -> list[HardRuleSpecDto]:
    """Retrieve all pre-tool dispatch hard invariant rules."""
    return service.get_rules()


@router.post(
    "/rules/toggle",
    summary="Enable or disable a specific hard invariant rule",
)
def toggle_rule(
    request: ToggleRuleRequest,
    service: PreToolUseInterceptorService = Depends(
        get_pre_tool_use_interceptor_service
    ),
) -> dict[str, bool]:
    """Toggle the enabled status of an existing hard rule."""
    success = service.toggle_rule(request.rule_id, request.enabled)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{request.rule_id}' not found.",
        )
    return {"success": True, "enabled": request.enabled}
