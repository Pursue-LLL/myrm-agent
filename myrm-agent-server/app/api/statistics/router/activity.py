"""[INPUT]
- .common (POS: shared router)

[OUTPUT]
- get_global_activity_patterns, get_top_sessions, get_nav_badges

[POS]
Statistics endpoints: activity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import Header, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log import EventLogAnalytics
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from sqlalchemy import func, select

from app.api.statistics.timezone_helper import resolve_user_timezone
from app.config.settings import settings
from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_session
from app.database.models import SystemNotification
from app.database.models.approval import ApprovalRecord
from app.database.models.cron import CronRunModel

from .common import router


@router.get("/activity")
async def get_global_activity_patterns(
    time_range_days: int | None = Query(None, ge=1, le=365, description="Time range in days (optional)"),
    timezone: str | None = Query(None, description="User local timezone, e.g. 'Asia/Shanghai'"),
    x_timezone: str | None = Header(None, alias="X-Timezone"),
) -> JSONResponse:
    """Get global activity patterns across all sessions.

    Returns daily breakdown, weekly patterns, busiest times, and activity streaks,
    bucketed by the user's local timezone.
    Requires EventLog data (only available for sessions created after EventLog integration).
    """
    try:
        _tz_info, tz_name = resolve_user_timezone(timezone, x_timezone)

        if not Path(settings.database.event_log_dir).exists():
            return success_response(
                data={
                    "timezone": tz_name,
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

        patterns = await analytics.get_global_activity_patterns(
            time_range_days=time_range_days,
            timezone=tz_name,
        )

        return success_response(
            data={
                "timezone": patterns.timezone,
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


@router.get("/badges")
async def get_nav_badges() -> JSONResponse:
    """Aggregate badge counts for NavBar: failed cron runs, pending approvals, unread notifications.

    Pending approvals combine goal-approval records with kanban tasks awaiting human review
    (IN_REVIEW), so the badge reflects every human-gated decision a user must make.
    All queries run concurrently for minimal latency.
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
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        async with get_session() as db:
            goal_pending = await db.scalar(
                select(func.count()).select_from(ApprovalRecord).where(ApprovalRecord.status == "PENDING")
            )
        kanban_review = await KanbanService.get_instance().count_tasks_by_status(TaskStatus.IN_REVIEW)
        return (goal_pending or 0) + kanban_review

    async def count_unread_notifications() -> int:
        async with get_session() as db:
            result = await db.scalar(
                select(func.count()).select_from(SystemNotification).where(SystemNotification.is_read == False)  # noqa: E712
            )
            return result or 0

    async def count_active_goals() -> int:
        from app.services.agent.goals.goal_controls import NON_TERMINAL_GOAL_STATUSES
        from app.services.agent.goals.goal_registry import GoalRegistry

        count = 0
        with GoalRegistry._lock:
            session_ids = list(GoalRegistry._providers.keys())
        for sid in session_ids:
            provider = GoalRegistry.get_provider(sid)
            if not provider:
                continue
            try:
                goal = await provider.get_latest_goal(sid)
                if goal and goal.status in NON_TERMINAL_GOAL_STATUSES:
                    count += 1
            except Exception:
                pass
        return count

    try:
        from app.services.extension.bridge import get_extension_bridge

        cron_failures, pending_approvals, unread_notifications, active_goals = await asyncio.gather(
            count_cron_failures(),
            count_pending_approvals(),
            count_unread_notifications(),
            count_active_goals(),
        )
        return success_response(
            data={
                "cronFailures": cron_failures,
                "pendingApprovals": pending_approvals,
                "unreadNotifications": unread_notifications,
                "activeGoals": active_goals,
                "total": cron_failures + pending_approvals + unread_notifications,
                "extensionConnected": get_extension_bridge().is_connected(),
            }
        )
    except Exception as e:
        raise internal_error(operation="Get nav badges", exception=e) from e
