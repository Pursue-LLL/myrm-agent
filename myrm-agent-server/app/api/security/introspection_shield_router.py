"""
[POS] app/api/security/introspection_shield_router.py
[INPUT] app.schemas.introspection_shield, app.services.security.introspection_shield_service
[OUTPUT] router

FastAPI router for Agent Runtime Introspection Shield & Decoupled Workspace Template Suite.
Exposes REST endpoints to intercept sandbox introspection probes, virtualize fake roots,
hydrate decoupled workspace standards, and scaffold starter templates.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.introspection_shield import (
    BlackholePatternsResponse,
    EvaluatePathProbeRequest,
    EvaluatePathProbeResponse,
    HydrateTemplatesRequest,
    HydrateTemplatesResponse,
    IntrospectionShieldMetricsResponse,
    ScaffoldTemplatesRequest,
    ScaffoldTemplatesResponse,
)
from app.services.security.introspection_shield_service import (
    IntrospectionShieldService,
    get_introspection_shield_service,
)

router = APIRouter(
    prefix="/introspection-shield",
    tags=["Agent Runtime Introspection Shield & Decoupled Workspace Templates"],
)


@router.post(
    "/evaluate-path",
    response_model=EvaluatePathProbeResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate an execution path probe against sandbox introspection blackholes",
)
def evaluate_path_probe(
    request: EvaluatePathProbeRequest,
    service: IntrospectionShieldService = Depends(get_introspection_shield_service),
) -> EvaluatePathProbeResponse:
    """Detect whether a file or directory probe accesses host topology or framework source."""
    return service.evaluate_path(request)


@router.post(
    "/hydrate-templates",
    response_model=HydrateTemplatesResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover and hydrate decoupled open standards templates from workspace",
)
def hydrate_templates(
    request: HydrateTemplatesRequest,
    service: IntrospectionShieldService = Depends(get_introspection_shield_service),
) -> HydrateTemplatesResponse:
    """Load SOUL.md, USER.md, IDENTITY.md, BOOTSTRAP.md, HEARTBEAT.md into prompt context."""
    return service.hydrate_templates(request)


@router.post(
    "/scaffold-templates",
    response_model=ScaffoldTemplatesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate baseline open standard starter templates in workspace root",
)
def scaffold_templates(
    request: ScaffoldTemplatesRequest,
    service: IntrospectionShieldService = Depends(get_introspection_shield_service),
) -> ScaffoldTemplatesResponse:
    """Create default decoupled workspace specification files."""
    return service.scaffold_templates(request)


@router.get(
    "/metrics",
    response_model=IntrospectionShieldMetricsResponse,
    summary="Get cumulative introspection shield operations metrics",
)
def get_metrics(
    service: IntrospectionShieldService = Depends(get_introspection_shield_service),
) -> IntrospectionShieldMetricsResponse:
    """Query total probes evaluated, blocked, fake roots, and hydrated templates."""
    return service.get_metrics()


@router.get(
    "/blackhole-patterns",
    response_model=BlackholePatternsResponse,
    summary="List active introspection blackhole matching patterns",
)
def get_blackhole_patterns(
    service: IntrospectionShieldService = Depends(get_introspection_shield_service),
) -> BlackholePatternsResponse:
    """Query active blackhole pattern list."""
    return service.get_blackhole_patterns()
