from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log import EventLogAnalytics
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.rate_limits import router as rate_limits_router
from app.api.statistics.session_analytics import router as session_router
from app.api.statistics.usage_aggregation import (
    DayAccumulator,
    aggregate_usage,
    extract_usage,
    normalize_usage_rows,
)
from app.config.settings import settings
from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db, get_session
from app.database.models import Chat, Message, SystemNotification
from app.database.models.agent import Agent
from app.database.models.approval import ApprovalRecord
from app.database.models.cron import CronRunModel

router = APIRouter()
router.include_router(session_router)
router.include_router(rate_limits_router)
logger = logging.getLogger(__name__)


def _parse_date(value: str, param_name: str) -> datetime:
    """Parse ISO date string to timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        raise validation_error(f"Invalid {param_name} format. Use ISO 8601 (e.g. 2025-01-01T00:00:00Z)") from e


@router.get("/usage")
async def get_usage_statistics(
    start: str | None = Query(None, description="ISO 8601 start date"),
    end: str | None = Query(None, description="ISO 8601 end date"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Aggregate token usage statistics for the current user.

    Scans assistant messages within the date range and aggregates
    token usage from extra_data.usage JSON fields.

    Returns total tokens, cost, cache efficiency, and per-model breakdown.
    """
    try:
        start_dt = _parse_date(start, "start") if start else None
        end_dt = _parse_date(end, "end") if end else None

        filters = [
            Message.chat_id == Chat.id,
            Message.role == "assistant",
            Message.extra_data.isnot(None),
        ]
        if start_dt:
            filters.append(Message.created_at >= start_dt)
        if end_dt:
            filters.append(Message.created_at <= end_dt)

        stmt = select(Message.extra_data, Message.created_at).where(and_(*filters)).order_by(Message.created_at.asc())

        result = await db.execute(stmt)
        rows = result.all()

        stats = aggregate_usage(normalize_usage_rows(rows))
        return success_response(data=stats)
    except Exception as e:
        if "validation" in type(e).__name__.lower():
            raise
        raise internal_error(operation="Get usage statistics", exception=e) from e


@router.get("/usage/radar")
async def get_usage_radar(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get O(1) aggregated global usage statistics for the user's dashboard.

    Aggregates total_calls, total_tokens, and total_usd directly from the Chat table.
    """
    try:
        stmt = select(
            func.sum(Chat.total_calls).label("total_calls"),
            func.sum(Chat.total_tokens).label("total_tokens"),
            func.sum(Chat.total_usd).label("total_usd"),
        )
        result = await db.execute(stmt)
        row = result.first()

        return success_response(
            data={
                "total_calls": row.total_calls or 0 if row else 0,
                "total_tokens": row.total_tokens or 0 if row else 0,
                "total_usd": round(row.total_usd or 0.0, 6) if row else 0.0,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get usage radar statistics", exception=e) from e


@router.get("/usage/by-agent")
async def get_usage_by_agent(
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get token usage breakdown grouped by agent.

    Aggregates total_calls, total_tokens, and total_usd from the Chat table
    grouped by agent_id, joined with Agent table for display metadata.
    Returns per-agent totals with percentage breakdown.
    """
    try:
        from datetime import timedelta

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        filters = [Chat.deleted_at.is_(None), Chat.created_at >= start_dt]

        stmt = (
            select(
                func.coalesce(Chat.agent_id, "default").label("agent_id"),
                func.sum(Chat.total_calls).label("calls"),
                func.sum(Chat.total_tokens).label("tokens"),
                func.sum(Chat.total_usd).label("cost_usd"),
                func.count(Chat.id).label("session_count"),
            )
            .where(and_(*filters))
            .group_by(func.coalesce(Chat.agent_id, "default"))
            .order_by(func.sum(Chat.total_usd).desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        agent_ids = [r.agent_id for r in rows if r.agent_id != "default"]
        agent_map: dict[str, tuple[str, str | None]] = {}
        if agent_ids:
            agent_stmt = select(Agent.id, Agent.name, Agent.avatar).where(Agent.id.in_(agent_ids))
            agent_result = await db.execute(agent_stmt)
            for agent_row in agent_result.all():
                agent_map[agent_row[0]] = (agent_row[1], agent_row[2])

        grand_total_tokens = sum(r.tokens or 0 for r in rows)
        grand_total_usd = sum(r.cost_usd or 0.0 for r in rows)

        agents = []
        for row in rows:
            agent_id = row.agent_id
            name, avatar = agent_map.get(agent_id, (None, None))
            if agent_id == "default" and name is None:
                name = "Default Agent"

            tokens = row.tokens or 0
            cost_usd = row.cost_usd or 0.0

            agents.append(
                {
                    "agentId": agent_id,
                    "name": name or agent_id,
                    "avatar": avatar,
                    "totalTokens": tokens,
                    "totalUsd": round(cost_usd, 6),
                    "totalCalls": row.calls or 0,
                    "sessions": row.session_count or 0,
                    "percentTokens": round(tokens / grand_total_tokens * 100, 1) if grand_total_tokens > 0 else 0.0,
                    "percentUsd": round(cost_usd / grand_total_usd * 100, 1) if grand_total_usd > 0 else 0.0,
                    "sparkline": [],
                }
            )

        return success_response(
            data={
                "agents": agents,
                "total_agents": len(agents),
                "grand_total_tokens": grand_total_tokens,
                "grand_total_usd": round(grand_total_usd, 6),
            }
        )
    except Exception as e:
        if "validation" in type(e).__name__.lower():
            raise
        raise internal_error(operation="Get usage by agent", exception=e) from e


@router.get("/usage/daily")
async def get_daily_usage(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get daily aggregated token usage for charting.

    Returns an array of daily usage summaries for the specified lookback period.
    """
    try:
        from datetime import timedelta

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        stmt = (
            select(Message.extra_data, Message.created_at)
            .where(
                and_(
                    Message.chat_id == Chat.id,
                    Message.role == "assistant",
                    Message.extra_data.isnot(None),
                    Message.created_at >= start_dt,
                )
            )
            .order_by(Message.created_at.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        daily_map: dict[str, DayAccumulator] = {}
        for extra_data, created_at in normalize_usage_rows(rows):
            usage = extract_usage(extra_data)
            if not usage or created_at is None:
                continue

            day_key = created_at.strftime("%Y-%m-%d")
            if day_key not in daily_map:
                daily_map[day_key] = DayAccumulator()
            daily_map[day_key].add(usage, extra_data)

        daily_list = [{"date": day, **acc.to_dict()} for day, acc in sorted(daily_map.items())]

        return success_response(
            data={
                "days": days,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "daily": daily_list,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get daily usage statistics", exception=e) from e


@router.get("/usage/sessions")
async def get_session_usage(
    limit: int = Query(20, ge=1, le=100, description="Max sessions to return"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get per-session token usage summaries, ordered by most recent.

    Useful for showing which conversations consumed the most tokens.
    """
    try:
        chat_stmt = (
            select(
                Chat.id,
                Chat.title,
                Chat.action_mode,
                Chat.created_at,
                func.count(Message.id).label("message_count"),
            )
            .join(Message, Message.chat_id == Chat.id)
            .group_by(Chat.id)
            .order_by(Chat.updated_at.desc())
            .limit(limit)
        )

        chat_result = await db.execute(chat_stmt)
        chat_rows = chat_result.all()

        if not chat_rows:
            return success_response(data={"sessions": []})

        chat_ids = [row[0] for row in chat_rows]

        msg_stmt = select(Message.chat_id, Message.extra_data).where(
            and_(
                Message.chat_id.in_(chat_ids),
                Message.role == "assistant",
                Message.extra_data.isnot(None),
            )
        )
        msg_result = await db.execute(msg_stmt)
        msg_by_chat: dict[str, list[tuple[dict[str, object] | None, datetime | None]]] = {}
        for row in msg_result.all():
            cells = tuple(row)
            if len(cells) < 2:
                continue
            chat_id_val, raw_extra = cells[0], cells[1]
            extra_dict = raw_extra if isinstance(raw_extra, dict) else None
            msg_by_chat.setdefault(str(chat_id_val), []).append((extra_dict, None))

        sessions = []
        for chat_id, title, action_mode, created_at, message_count in chat_rows:
            stats = aggregate_usage(msg_by_chat.get(chat_id, []))

            sessions.append(
                {
                    "chatId": chat_id,
                    "title": title or "Untitled",
                    "actionMode": action_mode,
                    "createdAt": created_at.isoformat() if created_at else None,
                    "messageCount": message_count,
                    **stats,
                }
            )

        return success_response(data={"sessions": sessions})
    except Exception as e:
        raise internal_error(operation="Get session usage statistics", exception=e) from e


@router.get("/tool-stability")
async def get_tool_stability(
    tool_name: str | None = Query(
        None,
        description="Optional tool name to filter by. If omitted, aggregates all tools.",
    ),
    time_range_days: int | None = Query(30, ge=1, le=365, description="Time range in days (optional, defaults to 30)"),
) -> JSONResponse:
    """Get global tool stability and performance metrics.

    Returns daily aggregated tool stability statistics, including success/failure counts,
    timeouts, failure rates, P90/P99 latency, and top failure reasons.
    """
    try:
        if not Path(settings.database.event_log_dir).exists():
            return success_response(
                data={
                    "daily_stability": [],
                    "global_total_calls": 0,
                    "global_failure_rate": 0.0,
                    "global_avg_duration_ms": 0.0,
                    "busiest_tool": "unknown",
                    "most_failed_tool": "unknown",
                }
            )

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)

        stability_data = await analytics.get_tool_stability(
            tool_name=tool_name,
            time_range_days=time_range_days,
        )

        return success_response(
            data={
                "daily_stability": [
                    {
                        "date": ds.date,
                        "tool_name": ds.tool_name,
                        "total_calls": ds.total_calls,
                        "success_count": ds.success_count,
                        "failure_count": ds.failure_count,
                        "timeout_count": ds.timeout_count,
                        "avg_duration_ms": ds.avg_duration_ms,
                        "p90_duration_ms": ds.p90_duration_ms,
                        "p99_duration_ms": ds.p99_duration_ms,
                        "failure_rate": ds.failure_rate,
                        "failure_reasons": ds.failure_reasons,
                    }
                    for ds in stability_data.daily_stability
                ],
                "global_total_calls": stability_data.global_total_calls,
                "global_failure_rate": stability_data.global_failure_rate,
                "global_avg_duration_ms": stability_data.global_avg_duration_ms,
                "busiest_tool": stability_data.busiest_tool,
                "most_failed_tool": stability_data.most_failed_tool,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get tool stability patterns", exception=e) from e


@router.get("/activity")
async def get_global_activity_patterns(
    time_range_days: int | None = Query(None, ge=1, le=365, description="Time range in days (optional)"),
) -> JSONResponse:
    """Get global activity patterns across all sessions.

    Returns daily breakdown, weekly patterns, busiest times, and activity streaks.
    Requires EventLog data (only available for sessions created after EventLog integration).
    """
    try:
        if not Path(settings.database.event_log_dir).exists():
            return success_response(
                data={
                    "daily_activities": [],
                    "by_day_of_week": {},
                    "by_hour": {},
                    "active_days": 0,
                    "max_streak": 0,
                    "busiest_day_of_week": 0,
                    "busiest_hour": 0,
                }
            )

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)

        patterns = await analytics.get_global_activity_patterns(time_range_days=time_range_days)

        return success_response(
            data={
                "timezone": "UTC",  # All timestamps and time-based calculations use UTC
                "daily_activities": [
                    {
                        "date": act.date,
                        "day_of_week": act.day_of_week,
                        "session_count": act.session_count,
                        "tool_calls": act.tool_calls,
                        "duration_ms": act.duration_ms,
                    }
                    for act in patterns.daily_activities
                ],
                "by_day_of_week": patterns.by_day_of_week,
                "by_hour": patterns.by_hour,
                "active_days": patterns.active_days,
                "max_streak": patterns.max_streak,
                "busiest_day_of_week": patterns.busiest_day_of_week,
                "busiest_hour": patterns.busiest_hour,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get global activity patterns", exception=e) from e


@router.get("/top-sessions")
async def get_top_sessions(
    metric: str = Query("duration", description="Ranking metric: duration, messages, tokens, tool_calls"),
    limit: int = Query(10, ge=1, le=50, description="Number of top sessions (1-50)"),
    time_range_days: int | None = Query(None, ge=1, le=365, description="Time range in days (optional)"),
) -> JSONResponse:
    """Get top N sessions ranked by specified metric.

    Supports flexible ranking by duration, messages, tokens, or tool calls.
    Returns TopSession records with comprehensive statistics.
    """
    try:
        if not Path(settings.database.event_log_dir).exists():
            return success_response(data=[])

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)

        top_sessions = await analytics.get_top_sessions(
            metric=metric,
            limit=limit,
            time_range_days=time_range_days,
        )

        return success_response(
            data=[
                {
                    "session_id": session.session_id,
                    "metric_value": session.metric_value,
                    "metric_type": session.metric_type,
                    "started_at": session.started_at,
                    "duration_ms": session.duration_ms,
                    "message_count": session.message_count,
                    "total_tokens": session.total_tokens,
                    "tool_calls": session.tool_calls,
                }
                for session in top_sessions
            ]
        )
    except ValueError as e:
        raise validation_error(message=str(e)) from e
    except Exception as e:
        raise internal_error(operation="Get top sessions", exception=e) from e


@router.get("/agent/{agent_id}/tool_health")
async def get_agent_tool_health(
    agent_id: str,
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
) -> JSONResponse:
    """Get aggregated tool health metrics for a specific agent.

    Queries the EventLog backend to return aggregated success rates,
    error counts, and durations per tool for the specified agent.
    """
    try:
        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)
        health_data = await analytics.get_agent_tool_health(agent_id=agent_id, days=days)
        return success_response(data=health_data)
    except Exception as e:
        raise internal_error(operation="Get agent tool health", exception=e) from e


@router.get("/badges")
async def get_nav_badges() -> JSONResponse:
    """Aggregate badge counts for NavBar: failed cron runs, pending approvals, unread notifications.

    All three queries run concurrently for minimal latency.
    """
    import asyncio
    from datetime import timedelta

    async def count_cron_failures() -> int:
        async with get_session() as db:
            twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            result = await db.scalar(
                select(func.count())
                .select_from(CronRunModel)
                .where(
                    CronRunModel.status.in_(("failed", "error")),
                    CronRunModel.started_at >= twenty_four_hours_ago,
                )
            )
            return result or 0

    async def count_pending_approvals() -> int:
        async with get_session() as db:
            result = await db.scalar(select(func.count()).select_from(ApprovalRecord).where(ApprovalRecord.status == "PENDING"))
            return result or 0

    async def count_unread_notifications() -> int:
        async with get_session() as db:
            result = await db.scalar(
                select(func.count()).select_from(SystemNotification).where(SystemNotification.is_read == False)  # noqa: E712
            )
            return result or 0

    try:
        cron_failures, pending_approvals, unread_notifications = await asyncio.gather(
            count_cron_failures(),
            count_pending_approvals(),
            count_unread_notifications(),
        )
        return success_response(
            data={
                "cronFailures": cron_failures,
                "pendingApprovals": pending_approvals,
                "unreadNotifications": unread_notifications,
                "total": cron_failures + pending_approvals + unread_notifications,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get nav badges", exception=e) from e
