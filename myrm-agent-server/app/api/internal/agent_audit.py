"""Control Plane → sandbox agent audit pull endpoint.

[INPUT]
- settings.database.event_log_dir (POS: harness JSONL event-log location)
- myrm_agent_harness.agent.event_log (POS: FileEventLogBackend + EventFilter)

[OUTPUT]
- GET /api/admin/agent-audit/events: read-only agent event pull for org audit

[POS]
Exposes the harness event log (the agent-event SSOT shared by all three
deployment modes) as an internal pull API for the control plane. This replaces
the removed AgentTurn/AgentEvent tables as the cloud compliance audit source.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import EventFilter
from pydantic import BaseModel

from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_CP_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_CP_TOKEN_HEADER = "X-Telemetry-Token"
_MAX_LIMIT = 1000
_DEFAULT_LIMIT = 200
_MAX_HOURS = 24 * 30


class AgentAuditEventResponse(BaseModel):
    seq: int
    ts: float
    type: str
    sid: str
    data: dict[str, object]


class AgentAuditQueryResponse(BaseModel):
    events: list[AgentAuditEventResponse]
    total: int
    window_hours: int
    limit: int


def _verify_cp_token(request: Request) -> None:
    expected = os.environ.get(_CP_TOKEN_ENV)
    if not expected:
        return
    token = request.headers.get(_CP_TOKEN_HEADER, "")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid CP token")


@router.get("/api/admin/agent-audit/events", response_model=AgentAuditQueryResponse)
async def agent_audit_events(
    request: Request,
    hours: int = 24,
    limit: int = _DEFAULT_LIMIT,
    session_id: str | None = None,
) -> AgentAuditQueryResponse:
    """Pull persisted agent events for the control-plane org audit fan-out."""
    _verify_cp_token(request)
    if hours < 1 or hours > _MAX_HOURS:
        raise HTTPException(status_code=400, detail="hours must be within [1, 720]")
    capped_limit = min(max(limit, 1), _MAX_LIMIT)

    log_dir = settings.database.event_log_dir
    if not os.path.isdir(log_dir):
        return AgentAuditQueryResponse(events=[], total=0, window_hours=hours, limit=capped_limit)

    start_time = time.time() - hours * 3600
    if session_id:
        session_ids = [session_id]
    else:
        probe = FileEventLogBackend(log_dir=log_dir, session_id="__probe__")
        session_ids = await probe.get_all_session_ids()

    collected: list[AgentAuditEventResponse] = []
    for sid in session_ids:
        backend = FileEventLogBackend(log_dir=log_dir, session_id=sid)
        events = await backend.get_events(
            sid,
            EventFilter(start_time=start_time, end_time=None, limit=None),
        )
        for event in events:
            collected.append(
                AgentAuditEventResponse(
                    seq=event.sequence,
                    ts=event.timestamp,
                    type=event.event_type,
                    sid=event.session_id,
                    data=event.data.model_dump(),
                )
            )

    collected.sort(key=lambda e: e.ts, reverse=True)
    total = len(collected)
    truncated = collected[:capped_limit]
    logger.info(
        "Agent audit pull: sessions=%d window_hours=%d total=%d returned=%d",
        len(session_ids),
        hours,
        total,
        len(truncated),
    )
    return AgentAuditQueryResponse(
        events=truncated,
        total=total,
        window_hours=hours,
        limit=capped_limit,
    )
