"""Cron job lifecycle actions REST endpoints.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- cron.schemas (POS: request/response Pydantic models)
- myrm_agent_harness.toolkits.cron.types::RunNowOutcome (POS: what a manual-run request came to)
- myrm_agent_harness.toolkits.cron.types::CronJob / JobResult (POS: cron job domain types the test payload is built from)
- myrm_agent_harness.toolkits.cron::CronManagerPort (POS: typing seam between the cron agent tools and the object that manages jobs)
- myrm_agent_harness.toolkits.cron.delivery::WebhookDelivery (POS: built-in webhook ResultDelivery for cron job results)
- core.cron.adapters.channel_delivery::ChannelResultDelivery (POS: ResultDelivery implementation via the Channel Gateway)
- core.cron.adapters.delivery_resolver::NON_OUTBOUND_CHANNELS (POS: business-layer cron delivery rules; the channels that deliver nowhere outside)
- core.infra.ingress_requirement::invalidate_ingress_requirement_cache (POS: single source of truth for the Ingress requirement)
- platform_utils.sandbox.entitlements.entitlement_guard::EntitlementGuardError (POS: resolves SaaS sandbox entitlements)

[OUTPUT]
- POST /{job_id}/duplicate — duplicate job with config, paused
- POST /{job_id}/pause — pause job
- POST /{job_id}/resume — resume job
- POST /{job_id}/trigger — start one manual trial run (202; 404 when missing or not active; 409 when already running)
- POST /{job_id}/test-delivery — send a one-off payload through the job's saved delivery, or the given not-yet-saved one (404 unknown job; 400 channel without outbound delivery; 502 delivery failed); the job itself is never modified
- POST /{job_id}/reset-baseline — reset monitor baseline

[POS]
Cron job operation endpoints. Job state changes are delegated to CronManager; the test-delivery endpoint sends a
fixed one-line payload through the delivery classes real runs use.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.cron import CronManagerPort
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, RunNowOutcome

from app.api.cron.schemas import (
    CronJobResponse,
    DeliveryTestRequest,
    DeliveryTestResponse,
)
from app.core.cron.adapters.delivery_resolver import NON_OUTBOUND_CHANNELS
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache

from . import helpers as _h

router = APIRouter()


@router.post("/{job_id}/duplicate", response_model=CronJobResponse, status_code=201)
async def duplicate_job(job_id: str) -> CronJobResponse:
    from app.platform_utils.sandbox.entitlements.entitlement_guard import (
        EntitlementGuardError,
    )

    mgr = _h._get_manager()
    try:
        job = await mgr.duplicate_job(job_id)
    except ValueError as exc:
        if isinstance(exc.__cause__, EntitlementGuardError):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()
    return _h._to_response(job)


@router.post("/{job_id}/pause", response_model=CronJobResponse)
async def pause_job(job_id: str) -> CronJobResponse:
    mgr = _h._get_manager()
    job = await mgr.pause_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _h._to_response(job)


@router.post("/{job_id}/resume", response_model=CronJobResponse)
async def resume_job(job_id: str) -> CronJobResponse:
    mgr = _h._get_manager()
    try:
        job = await mgr.resume_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _h._to_response(job)


@router.post("/{job_id}/trigger", status_code=202)
async def trigger_job(job_id: str) -> dict[str, bool]:
    """Start one manual trial run; the job's schedule and fire count are left alone."""
    outcome = await _h._get_manager().run_now(job_id)
    if outcome == RunNowOutcome.ALREADY_RUNNING:
        raise HTTPException(status_code=409, detail="Job is already running")
    if outcome != RunNowOutcome.STARTED:
        raise HTTPException(status_code=404, detail="Job not found or not active")
    return {"triggered": True}


async def _run_test_delivery(
    mgr: CronManagerPort,
    job_id: str,
    body: DeliveryTestRequest | None,
) -> DeliveryTestResponse:
    """Send a one-off test payload through the job's delivery channel.

    Omit the body to test the job's saved delivery; otherwise the provided
    (not-yet-saved) configuration is tested. The test reuses the real delivery
    classes (signing, SSRF guard, Feishu/WeCom bot formatting) but sends a fixed
    one-line text, and a webhook gets no retries and shorter timeouts. A pass
    shows the target accepts a request now; it does not promise that real runs
    deliver, because they send the task's output and the remote side changes.
    """
    from myrm_agent_harness.toolkits.cron.delivery import WebhookDelivery

    job = await mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if body is not None and (body.delivery or body.failure_delivery):
        if body.delivery is not None:
            config = _h._delivery_from_request(body.delivery, existing_secret=job.delivery.secret)
        else:
            existing_secret = job.failure_delivery.secret if job.failure_delivery else None
            config = _h._delivery_from_request(body.failure_delivery, existing_secret=existing_secret)
    else:
        config = job.delivery

    if config.channel in NON_OUTBOUND_CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=f"Channel '{config.channel}' does not support test delivery",
        )

    test_job = CronJob(
        id=job.id,
        name=job.name,
        job_type=job.job_type,
        schedule=job.schedule,
        delivery=config,
    )
    result = JobResult(
        success=True,
        output=f"Test delivery from Myrm scheduled task '{job.name}'",
        metadata={"model": None, "usage": None, "duration_ms": 0},
    )
    from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

    pipeline = ChannelResultDelivery(webhook_delivery=WebhookDelivery(max_retries=0, connect_timeout=5, read_timeout=15))
    try:
        await pipeline.deliver(test_job, result)
    except Exception as exc:
        # Some errors carry no text (httpx timeouts); the type name is all that says why.
        raise HTTPException(status_code=502, detail=f"Test delivery failed: {str(exc) or type(exc).__name__}") from exc

    return DeliveryTestResponse(delivered=True)


@router.post("/{job_id}/test-delivery", response_model=DeliveryTestResponse)
async def test_delivery(
    job_id: str,
    body: DeliveryTestRequest | None = None,
) -> DeliveryTestResponse:
    """Send a one-off test payload through the job's delivery channel."""
    mgr = _h._get_manager()
    return await _run_test_delivery(mgr, job_id, body)


@router.post("/{job_id}/reset-baseline")
async def reset_baseline(job_id: str) -> dict[str, bool]:
    mgr = _h._get_manager()
    reset = await mgr.reset_monitor_baseline(job_id)
    if not reset:
        raise HTTPException(status_code=404, detail="Job not found or no monitor baseline")
    return {"reset": True}
