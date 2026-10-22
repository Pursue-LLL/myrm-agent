"""FastAPI router for Orchestrator Scope Guardrails and Safe Team Design Mode (Item 37).

[INPUT]
- app.schemas.scope_guardrails::{AuditTeamScopeRequest, SafeTeamDesignConfigDTO, ...}
- app.services.agent.scope_guardrails_service::{ScopeGuardrailsService, get_scope_guardrails_service}

[OUTPUT]
- Router mounted under /chats/{chat_id}/scope-guardrails.

[POS]
- HTTP endpoints for team scope audits, least-privilege tool pruning, and safe design configuration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.scope_guardrails import (
    AuditTeamScopeRequest,
    SafeTeamDesignConfigDTO,
)
from app.services.agent.scope_guardrails_service import (
    ScopeGuardrailsService,
    get_scope_guardrails_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/scope-guardrails", tags=["Orchestrator Scope Guardrails"])


@router.post(
    "/audit",
    response_model=StandardSuccessResponse,
    summary="Audit proposed team roles and tools against least-privilege guardrails",
)
def audit_team_scope_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    req: AuditTeamScopeRequest = ...,
    service: ScopeGuardrailsService = Depends(get_scope_guardrails_service),
) -> StandardSuccessResponse:
    """Enforce minimum necessary permissions, strip forbidden tools, and cap excessive fan-out."""
    audit_res = service.audit_team_scope(req=req, session_id=chat_id)
    return create_success_response(data=audit_res)


@router.get(
    "/config",
    response_model=StandardSuccessResponse,
    summary="Get active safe team design configuration for session",
)
def get_session_config_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    service: ScopeGuardrailsService = Depends(get_scope_guardrails_service),
) -> StandardSuccessResponse:
    """Fetch active guardrails config (fan-out cap, forbidden tools, and per-role allowlists)."""
    cfg = service.get_active_config(session_id=chat_id)
    return create_success_response(data=cfg)


@router.put(
    "/config",
    response_model=StandardSuccessResponse,
    summary="Update custom safe team design guardrails for session",
)
def update_session_config_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    cfg: SafeTeamDesignConfigDTO = ...,
    service: ScopeGuardrailsService = Depends(get_scope_guardrails_service),
) -> StandardSuccessResponse:
    """Customize session guardrail thresholds and per-role tool allowlists."""
    updated = service.update_session_config(session_id=chat_id, cfg_dto=cfg)
    return create_success_response(data=updated)


@router.delete(
    "/config",
    response_model=StandardSuccessResponse,
    summary="Reset session guardrail configuration to system defaults",
)
def reset_session_config_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    service: ScopeGuardrailsService = Depends(get_scope_guardrails_service),
) -> StandardSuccessResponse:
    """Clear session overrides and revert to baseline safe team design mode."""
    service.reset_session_config(session_id=chat_id)
    return create_success_response(data={"reset": True, "chat_id": chat_id})
