"""
[POS] app/api/security/consumer_action_guard_router.py
[INPUT] app/schemas/consumer_action_guard.py, app/services/security/consumer_action_guard_service.py
[OUTPUT] router

FastAPI router for Consumer-Grade Real-World Action Explosion and Velocity Limiter Suite.

Exposes REST endpoints to evaluate high-risk consumer orders, record confirmed actions,
configure per-agent safety policies, and inspect telemetry metrics.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Path, status

from app.schemas.consumer_action_guard import (
    ConsumerGuardMetricsResponse,
    ConsumerGuardPolicySchema,
    ConsumerOrderConfirmRequest,
    ConsumerOrderConfirmResponse,
    ConsumerOrderEvaluateRequest,
    ConsumerOrderEvaluateResponse,
)
from app.services.security.consumer_action_guard_service import (
    ConsumerActionGuardService,
    get_consumer_action_guard_service,
)

router = APIRouter(
    prefix="/consumer-guard",
    tags=["Consumer Action Explosion & Velocity Guard"],
)


@router.post(
    "/evaluate-order",
    response_model=ConsumerOrderEvaluateResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate an outbound consumer order against multi-layered safety guardrails",
)
def evaluate_order(
    request: ConsumerOrderEvaluateRequest,
) -> ConsumerOrderEvaluateResponse:
    """Evaluate consumer order against quantity sanity assertions, velocity limiters, and daily ceilings."""
    service: ConsumerActionGuardService = get_consumer_action_guard_service()
    return service.evaluate_order(request)


@router.post(
    "/confirm-order",
    response_model=ConsumerOrderConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm execution of an order and update rolling daily spend tracker",
)
def confirm_order(
    request: ConsumerOrderConfirmRequest,
) -> ConsumerOrderConfirmResponse:
    """Record confirmed order and decrement remaining daily spend budget."""
    service: ConsumerActionGuardService = get_consumer_action_guard_service()
    return service.confirm_order(request)


@router.get(
    "/agents/{agent_id}/policy",
    response_model=ConsumerGuardPolicySchema,
    status_code=status.HTTP_200_OK,
    summary="Retrieve active consumer safety policy for an agent",
)
def get_agent_policy(
    agent_id: str = Path(..., min_length=1, description="Agent identifier"),
) -> ConsumerGuardPolicySchema:
    """Fetch safety policy and allowlists for the specified agent."""
    service: ConsumerActionGuardService = get_consumer_action_guard_service()
    return service.get_agent_policy(agent_id)


@router.put(
    "/agents/{agent_id}/policy",
    response_model=ConsumerGuardPolicySchema,
    status_code=status.HTTP_200_OK,
    summary="Configure safety policy and allowlists for an agent",
)
def update_agent_policy(
    policy: ConsumerGuardPolicySchema,
    agent_id: str = Path(..., min_length=1, description="Agent identifier"),
) -> ConsumerGuardPolicySchema:
    """Update quantity limits, velocity window, spend ceiling, and invariant destination allowlists."""
    service: ConsumerActionGuardService = get_consumer_action_guard_service()
    return service.set_agent_policy(agent_id, policy)


@router.get(
    "/metrics",
    response_model=ConsumerGuardMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect consumer action safety telemetry metrics",
)
def get_metrics() -> ConsumerGuardMetricsResponse:
    """Retrieve cumulative statistics across evaluations, HITL triggers, velocity rate limits, and blocks."""
    service: ConsumerActionGuardService = get_consumer_action_guard_service()
    return service.get_metrics()
