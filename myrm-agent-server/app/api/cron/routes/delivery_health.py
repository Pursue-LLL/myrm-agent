"""Delivery health REST endpoint for cron automations.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- app.services.cron.delivery_health_service::DeliveryHealthService (POS: judges a delivery destination from its delivery attempts)
- app.api.cron.schemas::DeliveryHealthResponse (POS: cron request/response Pydantic models)

[OUTPUT]
- GET /{job_id}/delivery-health — what the destination the job delivers to has done in the last day (404 unknown job; 204 without a body when there is no verdict)

[POS]
Server REST API router behind the delivery-health badge in a job's delivery settings.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.api.cron.schemas import DeliveryHealthResponse
from app.services.cron.delivery_health_service import DeliveryHealthService

from . import helpers as _h

router = APIRouter()

# A JSON ``null`` body would make the web client's ``apiRequest`` fail while it reads the body, so "no verdict" is the
# empty answer that client is built for.
_NO_VERDICT: dict[int | str, dict[str, str]] = {
    status.HTTP_204_NO_CONTENT: {
        "description": "No verdict: nothing leaves the application, or nothing was delivered there lately"
    },
}


@router.get("/{job_id}/delivery-health", response_model=DeliveryHealthResponse, responses=_NO_VERDICT)
async def get_delivery_health(job_id: str) -> DeliveryHealthResponse | Response:
    """The health of the destination the job's saved delivery names; 204 when there is no verdict."""
    job = await _h._get_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    health = await DeliveryHealthService.get_destination_health(job.delivery.channel, job.delivery.target)
    if health is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return DeliveryHealthResponse(
        status=health.status.value,
        failure_streak=health.failure_streak,
        last_error_category=health.last_error_category.value if health.last_error_category else None,
        last_failed_at=health.last_failed_at,
    )


__all__ = ["router"]
