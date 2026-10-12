"""API router for Semantic Layer RBAC & Private Fact Masking.

[INPUT]
- RegisterViewRequest, PlanSemanticQueryRequest, ExecuteSemanticQueryRequest.

[OUTPUT]
- Endpoints for semantic schema governance, query planning, and data filtering.

[POS]
- Server API. Mounted under /api/v1/security/semantic-rbac.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.core.security.semantic_rbac import (
    PrivateFactExposureError,
    SemanticRbacError,
)

from app.schemas.semantic_rbac import (
    ExecuteSemanticQueryRequest,
    ExecuteSemanticQueryResponse,
    PlanSemanticQueryRequest,
    RegisterViewRequest,
    SemanticQueryPlanDto,
    SemanticViewSchemaDto,
)
from app.services.security.semantic_rbac_service import (
    get_semantic_rbac_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/semantic-rbac", tags=["semantic-rbac"])


@router.post("/views", response_model=SemanticViewSchemaDto, status_code=status.HTTP_201_CREATED)
def register_semantic_view(req: RegisterViewRequest) -> SemanticViewSchemaDto:
    """Register or update a governed semantic view schema."""
    service = get_semantic_rbac_service()
    return service.register_view(req)


@router.get("/views/{view_name}", response_model=SemanticViewSchemaDto)
def get_semantic_view(view_name: str) -> SemanticViewSchemaDto:
    """Retrieve schema definitions for a semantic view."""
    service = get_semantic_rbac_service()
    view = service.get_view(view_name)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Semantic view '{view_name}' not found",
        )
    return view


@router.post("/plan", response_model=SemanticQueryPlanDto)
def plan_semantic_query(req: PlanSemanticQueryRequest) -> SemanticQueryPlanDto:
    """Plan a query applying identity row-level filtering and column access modifiers."""
    service = get_semantic_rbac_service()
    try:
        return service.plan_query(req)
    except PrivateFactExposureError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SemanticRbacError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/execute", response_model=ExecuteSemanticQueryResponse)
def execute_semantic_query(req: ExecuteSemanticQueryRequest) -> ExecuteSemanticQueryResponse:
    """Execute a governed semantic query against raw dataset with row/column RBAC."""
    service = get_semantic_rbac_service()
    try:
        return service.execute_query(req)
    except PrivateFactExposureError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SemanticRbacError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
