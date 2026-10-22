"""FastAPI router for Subagent Workspace Context Inheritance & Prompt Enrichment (Item 56).

[INPUT]
- app.schemas.workspace_inheritance::{
    InspectWorkspaceRulesRequest,
    EnrichChildPromptRequest,
  }
- app.services.agent.workspace_inheritance_service::{
    WorkspaceInheritanceService,
    get_workspace_inheritance_service,
  }

[OUTPUT]
- REST endpoints under /agents/workspace-inheritance for inspecting rules,
  enriching subagent prompts with inherited invariants, and auditing.

[POS]
- HTTP API layer for child agent workspace context inheritance and prompt enrichment.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.workspace_inheritance import (
    EnrichChildPromptRequest,
    InspectWorkspaceRulesRequest,
)
from app.services.agent.workspace_inheritance_service import (
    WorkspaceInheritanceService,
    get_workspace_inheritance_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/workspace-inheritance", tags=["Subagent Workspace Inheritance"])


@router.post(
    "/inspect-rules",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect workspace context rules along priority chain",
)
async def inspect_workspace_rules(
    req: InspectWorkspaceRulesRequest,
    service: WorkspaceInheritanceService = Depends(get_workspace_inheritance_service),
) -> StandardSuccessResponse:
    """Discover, parse, and evaluate rules in the workspace (.rules > AGENTS.md > README.md)."""
    result = service.inspect_workspace_rules(req)
    return create_success_response(data=result.model_dump())


@router.post(
    "/enrich-prompt",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Enrich subagent system prompt with inherited workspace rules",
)
async def enrich_child_prompt(
    req: EnrichChildPromptRequest,
    service: WorkspaceInheritanceService = Depends(get_workspace_inheritance_service),
) -> StandardSuccessResponse:
    """Enrich subagent base prompt by embedding workspace invariants under token budget capping."""
    result = service.enrich_child_prompt(req)
    return create_success_response(data=result.model_dump())


@router.get(
    "/audit-history",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recent workspace inheritance audit logs",
)
async def get_audit_history(
    service: WorkspaceInheritanceService = Depends(get_workspace_inheritance_service),
) -> StandardSuccessResponse:
    """Retrieve historical audit records documenting subagent workspace context inheritance."""
    history = service.get_audit_history()
    return create_success_response(data=history.model_dump())
