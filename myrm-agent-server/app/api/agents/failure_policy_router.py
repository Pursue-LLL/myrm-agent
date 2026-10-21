"""FastAPI router for Per-Role Subagent Failure Restart & Redeploy Policy (Item 35).

[INPUT]
- app.schemas.failure_policy::{RegisterRoleFailurePolicyRequest, ReportFailureEventRequest, ...}
- app.services.agent.failure_policy_service::{FailurePolicyService, get_failure_policy_service}

[OUTPUT]
- Router mounted under /chats/{chat_id}/failure-policy.

[POS]
- HTTP endpoints for role failure policy registration, autonomous remediation evaluations,
  decision history timelines, and retry counter resets.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query

from app.schemas.failure_policy import (
    RegisterRoleFailurePolicyRequest,
    ReportFailureEventRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.failure_policy_service import (
    FailurePolicyService,
    get_failure_policy_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/failure-policy", tags=["Subagent Failure Policy"])


@router.post(
    "/roles",
    response_model=StandardSuccessResponse,
    summary="Register or update failure remediation policy for a role",
)
def register_role_policy_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: RegisterRoleFailurePolicyRequest = ...,
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """Declare autonomous failure actions (restart_fresh, redeploy_specs, escalate, skip)."""
    policy = service.register_role_policy(session_id=chat_id, req=req)
    return create_success_response(data=policy)


@router.get(
    "/roles/{role_key}",
    response_model=StandardSuccessResponse,
    summary="Get active failure policy for a specific role",
)
def get_role_policy_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    role_key: str = Path(..., description="Subagent role identifier"),
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """Lookup failure policy by role_key with default fallback support."""
    policy = service.get_role_policy(session_id=chat_id, role_key=role_key)
    return create_success_response(data=policy)


@router.get(
    "/roles",
    response_model=StandardSuccessResponse,
    summary="List all declared failure policies in this chat session",
)
def list_role_policies_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """List all role failure recovery policies declared in session."""
    policies = service.list_role_policies(session_id=chat_id)
    return create_success_response(data=policies)


@router.post(
    "/evaluate",
    response_model=StandardSuccessResponse,
    summary="Report mid-task subagent failure and obtain autonomous remediation decision",
)
def evaluate_failure_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: ReportFailureEventRequest = ...,
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """Evaluate crash, timeout, or spec mismatch against role policy and decide remediation."""
    decision = service.report_and_evaluate_failure(
        session_id=chat_id,
        task_id=req.task_id,
        role_key=req.role_key,
        trigger_reason=req.trigger_reason,
        error_message=req.error_message,
        event_id=req.event_id,
    )
    return create_success_response(data=decision)


@router.get(
    "/history",
    response_model=StandardSuccessResponse,
    summary="Get history timeline of failure remediation decisions",
)
def get_decision_history_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    task_id: str | None = Query(None, description="Optional task identifier filter"),
    limit: int = Query(50, ge=1, le=200, description="Max history items"),
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """Fetch timeline of autonomous remediation decisions."""
    history = service.get_decision_history(session_id=chat_id, task_id=task_id, limit=limit)
    return create_success_response(data=history)


@router.post(
    "/tasks/{task_id}/reset-counter",
    response_model=StandardSuccessResponse,
    summary="Reset retry attempt counter for a subagent task",
)
def reset_task_counter_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    task_id: str = Path(..., description="Unique subagent task identifier"),
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """Reset retry count after human resolution or task re-dispatch."""
    service.reset_task_retry_counter(session_id=chat_id, task_id=task_id)
    return create_success_response(data={"reset": True, "task_id": task_id})


@router.delete(
    "",
    response_model=StandardSuccessResponse,
    summary="Purge all failure policies and decision state for the session",
)
def reset_session_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: FailurePolicyService = Depends(get_failure_policy_service),
) -> StandardSuccessResponse:
    """Clear all session failure policy data."""
    service.reset_session(session_id=chat_id)
    return create_success_response(data={"reset": True})
