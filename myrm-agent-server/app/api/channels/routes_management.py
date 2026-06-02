"""Channel routes management and health monitoring endpoints.

Provides runtime visibility into dynamically registered channel routes.

[INPUT]
- app.core.channel_bridge::channel_gateway
- app.infra.channel_routes.registry::ChannelRouteRegistry

[OUTPUT]
- router: FastAPI APIRouter for /channels/routes/*

[POS]
Routes management endpoints. Provides health reports and visibility
into dynamically registered channel HTTP routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class RouteHealthResponse(BaseModel):
    """Response model for route health report."""

    total_channels: int
    channels_with_routes: list[str]
    registered_channels_count: int
    total_routes: int
    routes_by_channel: dict[str, int]
    security_policy: dict[str, object]


_registry_instance: object | None = None


def set_route_registry(registry: object) -> None:
    """Set global route registry instance.

    Called by main.py during startup after routes are registered.

    Args:
        registry: ChannelRouteRegistry instance
    """
    global _registry_instance
    _registry_instance = registry


@router.get("/health", response_model=RouteHealthResponse)
async def get_routes_health(request: Request) -> RouteHealthResponse:
    """Get health report of all dynamically registered channel routes.

    Returns route registration statistics, channels with routes,
    and security policy information.

    Requires authentication.
    """
    if _registry_instance is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Route registry not initialized")

    from app.channels.implementations.fastapi import (
        ChannelRouteRegistry,
    )

    if not isinstance(_registry_instance, ChannelRouteRegistry):
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Invalid registry instance")

    report = _registry_instance.get_health_report()
    return RouteHealthResponse(**report)
