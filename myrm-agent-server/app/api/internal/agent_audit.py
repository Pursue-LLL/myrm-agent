"""Control Plane → sandbox agent audit pull endpoint.

[INPUT]
- settings.database.event_log_dir (POS: harness JSONL event-log location)
- myrm_agent_harness.agent.event_log (POS: FileEventLogBackend + EventFilter)

[OUTPUT]
- GET /api/admin/agent-audit/events: read-only agent event pull for org audit

[POS]
Exposes the harness event log (the agent-event SSOT shared by all three
deployment modes) as an internal pull API for the control plane's org-level
agent compliance audit.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import EventFilter
from pydantic import BaseModel

from app.config.settings import settings
from app.core.security.auth.control_plane_guard import verify_control_plane_token

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_control_plane_token)])
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
    tool_call_total: int
    security_event_total: int
    security_deny_total: int
    window_hours: int
    limit: int


# Harness 权威 deny 语义（myrm-agent-harness/core/security/audit.py record_decision 的
# policy_denial_total 口径）：决策字符串含 BLOCK/DENY/REDACT/LEAK 即为拦截类。
_DENY_TOKENS = ("BLOCK", "DENY", "REDACT", "LEAK")


def _is_deny_decision(decision: str) -> bool:
    return any(token in decision for token in _DENY_TOKENS)


@router.get("/api/admin/agent-audit/events", response_model=AgentAuditQueryResponse)
async def agent_audit_events(
    request: Request,
    hours: int = 24,
    limit: int = _DEFAULT_LIMIT,
    session_id: str | None = None,
) -> AgentAuditQueryResponse:
    """Pull persisted agent events for the control-plane org audit fan-out."""
    if hours < 1 or hours > _MAX_HOURS:
        raise HTTPException(status_code=400, detail="hours must be within [1, 720]")
    capped_limit = min(max(limit, 1), _MAX_LIMIT)

    log_dir = Path(settings.database.event_log_dir)
    if not os.path.isdir(log_dir):
        return AgentAuditQueryResponse(
            events=[],
            total=0,
            tool_call_total=0,
            security_event_total=0,
            security_deny_total=0,
            window_hours=hours,
            limit=capped_limit,
        )

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
    tool_call_total = sum(1 for e in collected if e.type == "tool_start")
    security_event_total = sum(1 for e in collected if e.type == "security_audit")
    security_deny_total = _count_security_denies(collected)
    truncated = collected[:capped_limit]
    logger.info(
        "Agent audit pull: sessions=%d window_hours=%d total=%d returned=%d tool_calls=%d security_events=%d security_denies=%d",
        len(session_ids),
        hours,
        total,
        len(truncated),
        tool_call_total,
        security_event_total,
        security_deny_total,
    )
    return AgentAuditQueryResponse(
        events=truncated,
        total=total,
        tool_call_total=tool_call_total,
        security_event_total=security_event_total,
        security_deny_total=security_deny_total,
        window_hours=hours,
        limit=capped_limit,
    )


def _count_security_denies(events: list[AgentAuditEventResponse]) -> int:
    """Count policy-denial decisions across all security_audit events."""
    deny_total = 0
    for event in events:
        if event.type != "security_audit":
            continue
        decisions = event.data.get("decisions")
        if not isinstance(decisions, list):
            continue
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            kind = decision.get("decision")
            if isinstance(kind, str) and _is_deny_decision(kind):
                deny_total += 1
    return deny_total
