"""Cron trigger dispatch REST endpoints.

[INPUT]
- cron.routes.helpers (POS: scheduler accessor)
- cron.schemas (POS: trigger dispatch Pydantic models)

[OUTPUT]
- POST /trigger/event — dispatch event trigger
- POST /trigger/system-event — dispatch system event trigger
- POST /trigger/webhook/{path} — dispatch webhook trigger

[POS]
Cron trigger dispatch REST endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.cron.schemas import (
    EventTriggerDispatchRequest,
    SystemEventTriggerDispatchRequest,
)
from app.services.agent.runtime_context import SINGLE_TENANT_USER_ID

from . import helpers as _h

router = APIRouter()


@router.post("/trigger/event")
async def dispatch_event(body: EventTriggerDispatchRequest) -> dict[str, int]:
    scheduler = _h._get_scheduler()
    count = await scheduler.dispatch_event(
        message=body.message,
        channel=body.channel,
        user_id=SINGLE_TENANT_USER_ID,
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
