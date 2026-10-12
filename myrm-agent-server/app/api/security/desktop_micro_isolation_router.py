"""API router for Desktop Host Auth & Tool Routing Micro-Isolation.

[INPUT]
- SanitizeEnvironmentRequest, RouteToolExecutionRequest.

[OUTPUT]
- Endpoints for purging host credentials, routing tools to micro-isolation or host,
  and disclosing system micro-isolation status.

[POS]
- Server API. Mounted under /api/v1/security/desktop-micro-isolation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.desktop_micro_isolation import (
    IsolationStatusDisclosureDto,
    RouteToolExecutionRequest,
    RouteToolExecutionResponse,
    SanitizeEnvironmentRequest,
    SanitizeEnvironmentResponse,
)
from app.services.security.desktop_micro_isolation_service import (
    get_desktop_micro_isolation_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desktop-micro-isolation", tags=["desktop-micro-isolation"])


@router.post("/sanitize-env", response_model=SanitizeEnvironmentResponse)
def sanitize_environment(req: SanitizeEnvironmentRequest) -> SanitizeEnvironmentResponse:
    """Purge sensitive host credentials (API keys, database URLs, tokens) from environment."""
    service = get_desktop_micro_isolation_service()
    return service.sanitize_env(req)


@router.post("/route-tool", response_model=RouteToolExecutionResponse)
def route_tool_execution(req: RouteToolExecutionRequest) -> RouteToolExecutionResponse:
    """Route tool invocation to micro-isolation or host process with credential & boundary enforcement."""
    service = get_desktop_micro_isolation_service()
    return service.route_tool_execution(req)


@router.get("/isolation-status", response_model=IsolationStatusDisclosureDto)
def get_isolation_status() -> IsolationStatusDisclosureDto:
    """Retrieve system disclosure of active tool micro-isolation capabilities and fail-closed state."""
    service = get_desktop_micro_isolation_service()
    return service.get_isolation_status()
