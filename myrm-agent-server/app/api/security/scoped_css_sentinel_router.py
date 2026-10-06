"""FastAPI router for Scoped CSS Isolation and Parallel Micro-Agent Boundary Sentinel.

[INPUT]
FastAPI APIRouter, dependencies, scoped CSS sentinel service and schemas.

[OUTPUT]
router: API endpoints for validating CSS stylesheet scoping and multi-agent layout specs.

[POS]
Router for scoped CSS sandbox isolation validation and micro-agent DOM protection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.scoped_css_sentinel import (
    CheckConflictRequest,
    CheckConflictResponse,
    ScopeCssRequest,
    ScopeCssResponse,
)
from app.services.security.scoped_css_sentinel_service import (
    ScopedCssSentinelService,
    get_scoped_css_sentinel_service,
)

router = APIRouter(prefix="/scoped-css-sentinel", tags=["scoped-css-sentinel"])


@router.post(
    "/scope",
    response_model=ScopeCssResponse,
    status_code=status.HTTP_200_OK,
    summary="Scope raw micro-agent CSS rules to target component container",
)
def scope_css(
    request: ScopeCssRequest,
    service: ScopedCssSentinelService = Depends(get_scoped_css_sentinel_service),
) -> ScopeCssResponse:
    """Enforce component scoping on style rules and prohibit unconfined global root selectors."""
    return service.scope_css(request)


@router.post(
    "/conflicts",
    response_model=CheckConflictResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate concurrent micro-agent style patches for target component collisions",
)
def check_conflicts(
    request: CheckConflictRequest,
    service: ScopedCssSentinelService = Depends(get_scoped_css_sentinel_service),
) -> CheckConflictResponse:
    """Check batch of concurrent patches for component collisions and global rule violations."""
    return service.check_conflicts(request)
