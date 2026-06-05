"""Daily journal API — aggregated view of a single day's agent activity.

Combines data from 6 existing sources (Chat, Message, ApprovalRecord,
CronRunModel, KanbanTaskEventModel, EventLog) into a unified daily
timeline view.  Zero new storage; pure aggregation of existing data.
DB queries execute sequentially (AsyncSession is not concurrency-safe);
EventLog query runs in parallel via create_task (file-based, no DB session).

[INPUT]
- app.database.models (POS: Chat, Message, ApprovalRecord, CronRunModel, KanbanTaskEventModel)
- myrm_agent_harness.agent.event_log (POS: EventLog file backend)

[OUTPUT]
- router: Daily journal APIRouter (get_daily_journal)

[POS]
Daily journal API. Provides a consolidated day-level view of all agent
activity across sessions, approvals, cron runs, kanban events, and tool calls.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.utils.errors import StandardHTTPException, internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat, Message
from app.database.models.approval import ApprovalRecord
from app.database.models.cron import CronRunModel
from app.database.models.kanban import KanbanTaskEventModel

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_day(value: str) -> tuple[datetime, datetime]:
    """Parse YYYY-MM-DD into (day_start_utc, day_end_utc)."""
    try:
        day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise validation_error("Invalid date format. Use YYYY-MM-DD.") from exc
    return day, day + timedelta(days=1)


# ── Data fetchers ────────────────────────────────────────────────────


async def _fetch_sessions(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    agent_id: str | None,
) -> list[dict[str, object]]:
    filters = [
        Chat.created_at >= start,
        Chat.created_at < end,
        Chat.deleted_at.is_(None),
    ]
    if agent_id:
        filters.append(Chat.agent_id == agent_id)

    stmt = (
        select(
            Chat.id,
            Chat.title,
            Chat.action_mode,
            Chat.source,
            Chat.agent_id,
            Chat.created_at,
            Chat.total_tokens,
            Chat.total_usd,
            Chat.total_calls,
        )
        .where(and_(*filters))
        .order_by(Chat.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    chat_ids = [r[0] for r in rows]
    msg_counts: dict[str, int] = {}
    if chat_ids:
        msg_stmt = select(Message.chat_id, func.count(Message.id)).where(Message.chat_id.in_(chat_ids)).group_by(Message.chat_id)
        msg_result = await db.execute(msg_stmt)
        msg_counts = dict(msg_result.all())

    return [
        {
            "chat_id": r[0],
            "title": r[1] or "Untitled",
            "action_mode": r[2],
            "source": r[3],
            "agent_id": r[4],
            "started_at": r[5].isoformat() if r[5] else None,
            "message_count": msg_counts.get(r[0], 0),
            "total_tokens": r[6] or 0,
            "total_usd": round(r[7] or 0.0, 6),
            "total_calls": r[8] or 0,
        }
        for r in rows
    ]


async def _fetch_approvals(db: AsyncSession, start: datetime, end: datetime) -> list[dict[str, object]]:
    stmt = (
        select(
            ApprovalRecord.id,
            ApprovalRecord.action_type,
            ApprovalRecord.status,
            ApprovalRecord.severity,
            ApprovalRecord.reason,
            ApprovalRecord.created_at,
            ApprovalRecord.resolved_at,
        )
        .where(and_(ApprovalRecord.created_at >= start, ApprovalRecord.created_at < end))
        .order_by(ApprovalRecord.created_at.asc())
    )
    result = await db.execute(stmt)
    return [
        {
            "id": r[0],
            "action_type": r[1],
            "status": r[2],
            "severity": r[3],
            "reason": (r[4] or "")[:200],
            "created_at": r[5].isoformat() if r[5] else None,
            "resolved_at": r[6].isoformat() if r[6] else None,
        }
        for r in result.all()
    ]


async def _fetch_cron_runs(db: AsyncSession, start: datetime, end: datetime) -> list[dict[str, object]]:
    stmt = (
        select(
            CronRunModel.id,
            CronRunModel.job_id,
            CronRunModel.status,
            CronRunModel.duration_ms,
            CronRunModel.started_at,
            CronRunModel.usage_total_tokens,
            CronRunModel.trigger_source,
        )
        .where(and_(CronRunModel.started_at >= start, CronRunModel.started_at < end))
        .order_by(CronRunModel.started_at.asc())
    )
    result = await db.execute(stmt)
    return [
        {
            "id": r[0],
            "job_id": r[1],
            "status": r[2],
            "duration_ms": r[3],
            "started_at": r[4].isoformat() if r[4] else None,
            "tokens": r[5] or 0,
            "trigger_source": r[6],
        }
        for r in result.all()
    ]


async def _fetch_kanban_events(db: AsyncSession, start: datetime, end: datetime) -> list[dict[str, object]]:
    stmt = (
        select(
            KanbanTaskEventModel.id,
            KanbanTaskEventModel.task_id,
            KanbanTaskEventModel.kind,
            KanbanTaskEventModel.created_at,
        )
        .where(
            and_(
                KanbanTaskEventModel.created_at >= start,
                KanbanTaskEventModel.created_at < end,
            )
        )
        .order_by(KanbanTaskEventModel.created_at.asc())
    )
    result = await db.execute(stmt)
    return [
        {
            "id": r[0],
            "task_id": r[1],
            "kind": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in result.all()
    ]


async def _fetch_tool_call_count(start: datetime, end: datetime) -> int:
    """Count tool calls from EventLog files within the date range."""
    event_log_dir = Path(settings.database.event_log_dir)
    if not event_log_dir.exists():
        return 0

    try:
        from myrm_agent_harness.agent.event_log import EventLogAnalytics
        from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend

        backend = FileEventLogBackend(log_dir=event_log_dir, session_id="default")
        analytics = EventLogAnalytics(backend)
        days_ago = max((datetime.now(timezone.utc) - start).days + 1, 2)
        patterns = await analytics.get_global_activity_patterns(time_range_days=days_ago)

        date_str = start.strftime("%Y-%m-%d")
        for act in patterns.daily_activities:
            if act.date == date_str:
                return act.tool_calls
    except Exception as exc:
        logger.debug("Failed to fetch tool call count: %s", exc)
    return 0


def _build_timeline(
    sessions: list[dict[str, object]],
    approvals: list[dict[str, object]],
    cron_runs: list[dict[str, object]],
    kanban_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Merge all event types into a single chronological timeline."""
    timeline: list[dict[str, object]] = []

    for s in sessions:
        timeline.append(
            {
                "time": s["started_at"],
                "type": "session",
                "title": s["title"],
                "detail": {
                    "chat_id": s["chat_id"],
                    "action_mode": s["action_mode"],
                    "tokens": s["total_tokens"],
                },
            }
        )

    for a in approvals:
        timeline.append(
            {
                "time": a["created_at"],
                "type": "approval",
                "title": f"{a['action_type']} — {a['status']}",
                "detail": {"id": a["id"], "severity": a["severity"]},
            }
        )

    for c in cron_runs:
        timeline.append(
            {
                "time": c["started_at"],
                "type": "cron_run",
                "title": f"Cron {c['job_id']} — {c['status']}",
                "detail": {"id": c["id"], "duration_ms": c["duration_ms"]},
            }
        )

    for k in kanban_events:
        timeline.append(
            {
                "time": k["created_at"],
                "type": "kanban",
                "title": f"Task {k['task_id']} — {k['kind']}",
                "detail": {"id": k["id"]},
            }
        )

    timeline.sort(key=lambda x: x.get("time") or "9999-12-31T23:59:59")
    return timeline


def _build_source_breakdown(sessions: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in sessions:
        src = str(s.get("source") or "unknown")
        counts[src] = counts.get(src, 0) + 1
    return counts


# ── Main endpoint ────────────────────────────────────────────────────


@router.get("/daily-journal")
async def get_daily_journal(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    agent_id: str | None = Query(None, description="Optional agent ID to filter sessions"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get consolidated daily work journal for a single day.

    Aggregates sessions, approvals, cron runs, kanban events, and tool calls
    into a unified timeline view.  Zero new storage; pure read-only aggregation.
    """
    try:
        day_start, day_end = _parse_day(date)

        tool_calls_task = asyncio.create_task(_fetch_tool_call_count(day_start, day_end))

        sessions = await _fetch_sessions(db, day_start, day_end, agent_id)
        approvals = await _fetch_approvals(db, day_start, day_end)
        cron_runs = await _fetch_cron_runs(db, day_start, day_end)
        kanban_events = await _fetch_kanban_events(db, day_start, day_end)

        tool_calls = await tool_calls_task

        total_tokens = sum(int(s.get("total_tokens", 0)) for s in sessions)
        total_usd = sum(float(s.get("total_usd", 0)) for s in sessions)

        return success_response(
            data={
                "date": date,
                "overview": {
                    "total_sessions": len(sessions),
                    "total_tokens": total_tokens,
                    "total_cost_usd": round(total_usd, 6),
                    "total_tool_calls": tool_calls,
                    "total_approvals": len(approvals),
                    "total_cron_runs": len(cron_runs),
                    "total_kanban_events": len(kanban_events),
                    "sessions_by_source": _build_source_breakdown(sessions),
                },
                "sessions": sessions,
                "approvals": approvals,
                "cron_runs": cron_runs,
                "kanban_events": kanban_events,
                "timeline": _build_timeline(sessions, approvals, cron_runs, kanban_events),
            }
        )
    except StandardHTTPException:
        raise
    except Exception as exc:
        raise internal_error(operation="Get daily journal", exception=exc) from exc
