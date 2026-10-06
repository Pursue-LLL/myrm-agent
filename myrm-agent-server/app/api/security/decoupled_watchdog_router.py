"""
[POS] app/api/security/decoupled_watchdog_router.py
[INPUT] app/schemas/decoupled_watchdog.py, app/services/security/decoupled_watchdog_service.py
[OUTPUT] router

FastAPI router for decoupled action watchdog and inbound multimodal content firewall suite.

Exposes REST endpoints to sanitize inbound external content, inspect proposed
actions against intent invariants, and retrieve telemetry metrics.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.decoupled_watchdog import (
    FirewallSanitizeRequest,
    FirewallSanitizeResponse,
    InvarianceAssertionRuleSchema,
    WatchdogInspectRequest,
    WatchdogInspectResponse,
    WatchdogMetricsResponse,
)
from app.services.security.decoupled_watchdog_service import (
    DecoupledWatchdogService,
    get_decoupled_watchdog_service,
)

router = APIRouter(
    prefix="/decoupled-watchdog",
    tags=["Decoupled Action Watchdog"],
)


@router.post(
    "/firewall/sanitize",
    response_model=FirewallSanitizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Sanitize inbound multimodal content",
)
def sanitize_inbound_content(
    request: FirewallSanitizeRequest,
) -> FirewallSanitizeResponse:
    """Sanitize external multimodal content by stripping invisible styles, steganography, and system headers."""
    service: DecoupledWatchdogService = get_decoupled_watchdog_service()
    return service.sanitize_inbound_content(request)


@router.post(
    "/watchdog/inspect",
    response_model=WatchdogInspectResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect proposed action against intent invariants",
)
def inspect_proposed_action(
    request: WatchdogInspectRequest,
) -> WatchdogInspectResponse:
    """Perform decoupled action inspection and detect parameter/amount drift before physical execution."""
    service: DecoupledWatchdogService = get_decoupled_watchdog_service()
    return service.inspect_action(request)


@router.post(
    "/rules",
    status_code=status.HTTP_200_OK,
    summary="Register safety invariance rule",
)
def register_invariance_rule(
    rule: InvarianceAssertionRuleSchema,
) -> dict[str, str]:
    """Register or configure a semantic invariance rule for a target tool."""
    service: DecoupledWatchdogService = get_decoupled_watchdog_service()
    service.register_rule(rule)
    return {"status": "rule_registered", "detail": f"Invariance rule '{rule.rule_name}' registered successfully"}


@router.get(
    "/metrics",
    response_model=WatchdogMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get watchdog operational metrics",
)
def get_watchdog_metrics() -> WatchdogMetricsResponse:
    """Retrieve operational telemetry and circuit breaker trip statistics."""
    service: DecoupledWatchdogService = get_decoupled_watchdog_service()
    return service.get_metrics()
