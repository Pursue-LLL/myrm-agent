"""Cron trigger dispatch and integrity verification REST endpoints.

[INPUT]
- cron.routes.helpers (POS: scheduler accessor)
- cron.schemas (POS: trigger dispatch and integrity Pydantic models)
- myrm_agent_harness.toolkits.cron.engine.integrity (POS: Merkle chain verification)

[OUTPUT]
- POST /trigger/event — dispatch event trigger
- POST /trigger/system-event — dispatch system event trigger
- POST /trigger/webhook/{path} — dispatch webhook trigger
- POST /{job_id}/verify-integrity — verify run integrity chain

[POS]
Cron trigger dispatch and integrity verification REST endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.cron.schemas import (
    ChainBreakResponse,
    EventTriggerDispatchRequest,
    IntegrityVerifyResponse,
    SystemEventTriggerDispatchRequest,
)

from . import helpers as _h

router = APIRouter()

USER_ID = "default"


@router.post("/trigger/event")
async def dispatch_event(body: EventTriggerDispatchRequest) -> dict[str, int]:
    scheduler = _h._get_scheduler()
    count = await scheduler.dispatch_event(
        message=body.message,
        channel=body.channel,
        user_id=USER_ID,
    )
    return {"triggered": count}


@router.post("/trigger/system-event")
async def dispatch_system_event(body: SystemEventTriggerDispatchRequest) -> dict[str, int]:
    scheduler = _h._get_scheduler()
    count = await scheduler.dispatch_system_event(
        source=body.source,
        event_type=body.event_type,
        payload=body.payload,
    )
    return {"triggered": count}


@router.post("/trigger/webhook/{path:path}")
async def dispatch_webhook(path: str, request: Request) -> dict[str, bool]:
    secret = request.headers.get("x-webhook-secret", "")
    if not secret:
        raise HTTPException(status_code=401, detail="Missing x-webhook-secret header")

    try:
        payload: dict[str, object] = await request.json()
    except Exception:
        payload = {}

    scheduler = _h._get_scheduler()
    job = await scheduler.dispatch_webhook(path=path, secret=secret, payload=payload)
    if job is None:
        raise HTTPException(status_code=404, detail="No matching webhook trigger")
    return {"triggered": True}


@router.post("/{job_id}/verify-integrity", response_model=IntegrityVerifyResponse)
async def verify_integrity(job_id: str) -> IntegrityVerifyResponse:
    from myrm_agent_harness.toolkits.cron.engine.integrity import verify_chain

    mgr = _h._get_manager()
    job = await mgr.get_job(job_id, USER_ID)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    runs = await mgr.list_runs(USER_ID, job_id=job_id, limit=10_000, offset=0)
    runs_sorted = sorted(runs, key=lambda r: r.started_at)
    verified_runs = [r for r in runs_sorted if r.integrity_hash]

    breaks = verify_chain(runs_sorted)
    return IntegrityVerifyResponse(
        job_id=job_id,
        total_runs=len(runs_sorted),
        verified_runs=len(verified_runs),
        intact=len(breaks) == 0,
        breaks=[
            ChainBreakResponse(
                run_id=b.run_id,
                kind=b.kind,
                expected=b.expected,
                actual=b.actual,
            )
            for b in breaks
        ],
    )
