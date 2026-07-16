"""Growth Dashboard API — aggregated view of agent growth metrics.

Combines data from multiple existing sources (memory stats, activity patterns,
skill evolution, companion evolution) into a single endpoint for the
Growth Dashboard frontend page.

Zero new storage; pure aggregation of existing data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log import EventLogAnalytics
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.usage_aggregation import (
    DayAccumulator,
    TierAccumulator,
    compute_estimated_savings,
    extract_usage,
    normalize_tier,
)
from app.config.settings import settings
from app.core.skills.store.service import skills_service
from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat, Message
from app.services.skills.experience_ledger import summarize_skill_growth_events
from app.services.skills.growth_audit_queries import list_skill_growth_timeline

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Response schemas ─────────────────────────────────────────────────


class GrowthSnapshot(BaseModel):
    """Top-level KPI cards."""

    total_memories: int = 0
    memory_by_type: dict[str, int] = Field(default_factory=dict)
    memory_week_delta: int = 0
    total_skills: int = 0
    total_evolutions: int = 0
    evolutions_approved: int = 0
    evolutions_rejected: int = 0
    evolutions_pending: int = 0
    evolutions_apply_failed: int = 0
    active_days: int = 0
    max_streak: int = 0
    memory_health_score: int = 100
    memory_health_dimensions: dict[str, float] = Field(default_factory=dict)


class ActivityDay(BaseModel):
    """Single cell in the activity heatmap."""

    date: str
    count: int = 0


class WeeklySummary(BaseModel):
    """This-week summary with previous-week comparison for delta display."""

    cron_executions: int = 0
    conversations: int = 0
    messages_sent: int = 0
    tool_calls: int = 0

    previous_cron_executions: int = 0
    previous_conversations: int = 0
    previous_messages_sent: int = 0
    previous_tool_calls: int = 0


class SkillEvolutionEvent(BaseModel):
    """Recent skill evolution log entry."""

    skill_id: str | None = None
    skill_name: str
    source: str
    status: str
    growth_type: str
    created_at: str
    change_summary: str = ""


class CostSummary(BaseModel):
    """Aggregated cost/savings for the dashboard time range."""

    total_cost_usd: float = 0.0
    cache_savings_usd: float = 0.0
    routing_savings: float = 0.0
    routing_savings_percent: float = 0.0
    total_savings_usd: float = 0.0


class SkillTrendPoint(BaseModel):
    """Single data point in a skill usage trend."""

    date: str
    success_rate: float
    avg_duration_ms: float
    call_count: int


class SkillTrendSeries(BaseModel):
    """Weekly aggregated usage trend for a single skill."""

    skill_name: str
    data_points: list[SkillTrendPoint]


class GrowthDashboardResponse(BaseModel):
    """Full dashboard payload — single GET returns everything."""

    snapshot: GrowthSnapshot
    activity_heatmap: list[ActivityDay]
    weekly_summary: WeeklySummary
    skill_events: list[SkillEvolutionEvent]
    cost_summary: CostSummary | None = None
    skill_trends: list[SkillTrendSeries] = Field(default_factory=list)


# ── Data fetchers (all read-only, no framework mutation) ─────────────


async def _fetch_memory_snapshot() -> tuple[dict[str, int], int, dict[str, float], int]:
    """Fetch memory counts by type via MemoryManager.

    Returns (by_type, health_score, dimensions, week_delta).
    """
    try:
        from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
        from app.services.agent.platform_config import require_platform_embedding_config

        embedding_cfg = await require_platform_embedding_config()

        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_cfg,
            approval_required=False,
        )
        week_start = datetime.now(UTC) - timedelta(days=7)
        by_type: dict[str, int] = {}
        week_delta = 0

        for mem_type in manager.get_enabled_types():
            try:
                count = await manager.count_memories(mem_type)
                by_type[mem_type.value] = count
            except Exception:
                by_type[mem_type.value] = 0
            try:
                week_count = await manager.count_memories(mem_type, since=week_start)
                week_delta += week_count
            except Exception as exc:
                logger.debug("Failed to count %s memories for week delta: %s", mem_type.value, exc)

        health_score = 100
        health_dims: dict[str, float] = {}
        try:
            health = await manager.compute_health_score()
            health_score = health.total
            health_dims = dict(health.dimensions)
        except Exception as exc:
            logger.debug("Failed to compute health score: %s", exc)

        return by_type, health_score, health_dims, week_delta
    except Exception as e:
        logger.warning("Failed to fetch memory snapshot: %s", e)
        return {}, 100, {}, 0


class _ActivitySnapshot:
    __slots__ = ("active_days", "max_streak", "heatmap", "tool_calls_this_week", "tool_calls_prev_week")

    def __init__(
        self,
        active_days: int = 0,
        max_streak: int = 0,
        heatmap: list[ActivityDay] | None = None,
        tool_calls_this_week: int = 0,
        tool_calls_prev_week: int = 0,
    ) -> None:
        self.active_days = active_days
        self.max_streak = max_streak
        self.heatmap = heatmap or []
        self.tool_calls_this_week = tool_calls_this_week
        self.tool_calls_prev_week = tool_calls_prev_week


async def _fetch_activity_data(time_range_days: int) -> _ActivitySnapshot:
    """Fetch activity metrics from EventLog including weekly tool_calls aggregation."""
    if not Path(settings.database.event_log_dir).exists():
        return _ActivitySnapshot()

    try:
        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)
        patterns = await analytics.get_global_activity_patterns(time_range_days=time_range_days)

        heatmap = [ActivityDay(date=act.date, count=act.session_count) for act in patterns.daily_activities]

        today = datetime.now(UTC).date()
        week_ago = today - timedelta(days=7)
        two_weeks_ago = today - timedelta(days=14)

        from datetime import date as date_cls

        tool_calls_this_week = 0
        tool_calls_prev_week = 0
        for act in patterns.daily_activities:
            act_date = date_cls.fromisoformat(act.date)
            if act_date >= week_ago:
                tool_calls_this_week += act.tool_calls
            elif act_date >= two_weeks_ago:
                tool_calls_prev_week += act.tool_calls

        return _ActivitySnapshot(
            active_days=patterns.active_days,
            max_streak=patterns.max_streak,
            heatmap=heatmap,
            tool_calls_this_week=tool_calls_this_week,
            tool_calls_prev_week=tool_calls_prev_week,
        )
    except Exception as e:
        logger.warning("Failed to fetch activity data: %s", e)
        return _ActivitySnapshot()


class _SkillEvolutionSnapshot:
    __slots__ = ("total_skills", "total_evolutions", "approved", "rejected", "pending", "apply_failed", "events")

    def __init__(
        self,
        total_skills: int = 0,
        total_evolutions: int = 0,
        approved: int = 0,
        rejected: int = 0,
        pending: int = 0,
        apply_failed: int = 0,
        events: list[SkillEvolutionEvent] | None = None,
    ) -> None:
        self.total_skills = total_skills
        self.total_evolutions = total_evolutions
        self.approved = approved
        self.rejected = rejected
        self.pending = pending
        self.apply_failed = apply_failed
        self.events = events or []


async def _fetch_skill_evolution_data() -> _SkillEvolutionSnapshot:
    """Fetch skill inventory + recent growth timeline from unified services."""
    try:
        skills = await skills_service.list_skills()
        total_skills = len(skills)
        summary = await summarize_skill_growth_events()
        timeline = await list_skill_growth_timeline(limit=20)
        events = [
            SkillEvolutionEvent(
                skill_id=item.skill_id,
                skill_name=item.skill_name,
                source=item.source.value,
                status=item.status.value,
                growth_type=item.growth_type,
                created_at=item.created_at.isoformat(),
                change_summary=item.change_summary,
            )
            for item in timeline
        ]
        return _SkillEvolutionSnapshot(
            total_skills=total_skills,
            total_evolutions=summary.total_events,
            approved=summary.approved,
            rejected=summary.rejected,
            pending=summary.pending_events,
            apply_failed=summary.apply_failed,
            events=events,
        )
    except Exception as e:
        logger.warning("Failed to fetch skill evolution data: %s", e)
        return _SkillEvolutionSnapshot()


class _DayBucket:
    __slots__ = ("total", "successes", "durations")

    def __init__(self) -> None:
        self.total = 0
        self.successes = 0
        self.durations: list[float] = []


async def _fetch_skill_trends() -> list[SkillTrendSeries]:
    """Aggregate per-skill usage_history into daily trend series."""
    try:
        from collections import defaultdict

        from app.core.skills.curator_service import get_stats_collector
        from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

        collector = get_stats_collector()
        result: list[SkillTrendSeries] = []

        for skill_root in DEFAULT_LOCAL_SKILL_PATHS:
            expanded = Path(skill_root).expanduser()
            if not expanded.exists():
                continue
            for skill_dir in expanded.iterdir():
                if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                    continue
                stats = collector.get_stats(skill_dir)
                if not stats.usage_history:
                    continue

                daily: dict[str, _DayBucket] = defaultdict(_DayBucket)
                for record in stats.usage_history:
                    day_key = record.timestamp[:10]
                    bucket = daily[day_key]
                    bucket.total += 1
                    if record.success:
                        bucket.successes += 1
                    bucket.durations.append(record.duration_ms)

                data_points = []
                for date_key in sorted(daily.keys()):
                    bucket = daily[date_key]
                    avg_dur = sum(bucket.durations) / len(bucket.durations) if bucket.durations else 0.0
                    data_points.append(
                        SkillTrendPoint(
                            date=date_key,
                            success_rate=bucket.successes / bucket.total if bucket.total > 0 else 0.0,
                            avg_duration_ms=round(avg_dur, 1),
                            call_count=bucket.total,
                        )
                    )

                if data_points:
                    result.append(SkillTrendSeries(skill_name=skill_dir.name, data_points=data_points))

        return result
    except Exception as e:
        logger.warning("Failed to fetch skill trends: %s", e)
        return []


async def _fetch_cost_summary(db: AsyncSession, time_range_days: int) -> CostSummary | None:
    """Aggregate cost savings from message extra_data within the time range."""
    try:
        cutoff = datetime.now(UTC) - timedelta(days=time_range_days)
        stmt = select(Message.extra_data).where(
            and_(
                Message.role == "assistant",
                Message.created_at >= cutoff,
                Message.extra_data.isnot(None),
            )
        ).limit(10000)
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return None

        acc = DayAccumulator()
        tier_accs: dict[str, TierAccumulator] = {}

        for extra_data in rows:
            if not isinstance(extra_data, dict):
                continue
            usage = extract_usage(extra_data)
            if not usage:
                continue
            acc.add(usage, extra_data)
            tier = normalize_tier(extra_data.get("routingTier"))
            if tier:
                if tier not in tier_accs:
                    tier_accs[tier] = TierAccumulator()
                tier_accs[tier].add(usage, extra_data)

        if acc.calls == 0:
            return None

        routing_savings_data = compute_estimated_savings(tier_accs)
        routing_savings = float(routing_savings_data["savings"]) if routing_savings_data else 0.0
        routing_savings_pct = float(routing_savings_data["savingsPercent"]) if routing_savings_data else 0.0

        total_savings = acc.cache_savings_usd + routing_savings
        if total_savings <= 0 and acc.cost_usd <= 0:
            return None

        return CostSummary(
            total_cost_usd=round(acc.cost_usd, 4),
            cache_savings_usd=round(acc.cache_savings_usd, 4),
            routing_savings=round(routing_savings, 4),
            routing_savings_percent=round(routing_savings_pct, 1),
            total_savings_usd=round(total_savings, 4),
        )
    except Exception as e:
        logger.warning("Failed to fetch cost summary: %s", e)
        return None


async def _fetch_weekly_summary(db: AsyncSession) -> WeeklySummary:
    """Fetch this-week and previous-week conversation/message/cron counts from DB."""
    try:
        now = datetime.now(UTC)
        week_start = now - timedelta(days=7)
        prev_week_start = now - timedelta(days=14)

        user_chats = select(Chat.id).subquery()

        conv_this_q = select(func.count()).select_from(Chat).where(Chat.created_at >= week_start)
        conv_prev_q = (
            select(func.count()).select_from(Chat).where(and_(Chat.created_at >= prev_week_start, Chat.created_at < week_start))
        )

        msg_this_q = select(func.count(Message.id)).where(
            and_(
                Message.chat_id.in_(select(user_chats.c.id)),
                Message.role == "user",
                Message.created_at >= week_start,
            )
        )
        msg_prev_q = select(func.count(Message.id)).where(
            and_(
                Message.chat_id.in_(select(user_chats.c.id)),
                Message.role == "user",
                Message.created_at >= prev_week_start,
                Message.created_at < week_start,
            )
        )

        conv_count = (await db.execute(conv_this_q)).scalar() or 0
        conv_prev = (await db.execute(conv_prev_q)).scalar() or 0
        msg_count = (await db.execute(msg_this_q)).scalar() or 0
        msg_prev = (await db.execute(msg_prev_q)).scalar() or 0

        cron_count = 0
        cron_prev = 0
        try:
            from app.core.cron.adapters.setup import get_cron_manager

            cron_mgr = get_cron_manager()
            if cron_mgr:
                history = await cron_mgr.get_execution_history(limit=400)
                week_start_ts = week_start.timestamp()
                prev_week_start_ts = prev_week_start.timestamp()
                for h in history:
                    started = getattr(h, "started_at", 0)
                    if started >= week_start_ts:
                        cron_count += 1
                    elif started >= prev_week_start_ts:
                        cron_prev += 1
        except Exception as exc:
            logger.debug("Failed to count cron executions: %s", exc)

        return WeeklySummary(
            cron_executions=cron_count,
            conversations=int(conv_count),
            messages_sent=int(msg_count),
            previous_cron_executions=cron_prev,
            previous_conversations=int(conv_prev),
            previous_messages_sent=int(msg_prev),
        )
    except Exception as e:
        logger.warning("Failed to fetch weekly summary: %s", e)
        return WeeklySummary()


# ── Main endpoint ────────────────────────────────────────────────────


@router.get("/growth-dashboard")
async def get_growth_dashboard(
    days: int = Query(84, ge=7, le=365, description="Heatmap lookback days (default 84 = 12 weeks)"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Aggregated growth dashboard — single endpoint, zero new storage.

    Combines: memory stats, activity heatmap, skill evolution, weekly summary.
    All data sources are read-only and already exist.
    """
    try:
        (
            (memory_by_type, health_score, health_dims, week_delta),
            activity,
            weekly,
            skill_snapshot,
            cost_summary,
            skill_trends,
        ) = await asyncio.gather(
            _fetch_memory_snapshot(),
            _fetch_activity_data(days),
            _fetch_weekly_summary(db),
            _fetch_skill_evolution_data(),
            _fetch_cost_summary(db, days),
            _fetch_skill_trends(),
        )

        total_memories = sum(memory_by_type.values())

        weekly.tool_calls = activity.tool_calls_this_week
        weekly.previous_tool_calls = activity.tool_calls_prev_week

        dashboard = GrowthDashboardResponse(
            snapshot=GrowthSnapshot(
                total_memories=total_memories,
                memory_by_type=memory_by_type,
                memory_week_delta=week_delta,
                total_skills=skill_snapshot.total_skills,
                total_evolutions=skill_snapshot.total_evolutions,
                evolutions_approved=skill_snapshot.approved,
                evolutions_rejected=skill_snapshot.rejected,
                evolutions_pending=skill_snapshot.pending,
                evolutions_apply_failed=skill_snapshot.apply_failed,
                active_days=activity.active_days,
                max_streak=activity.max_streak,
                memory_health_score=health_score,
                memory_health_dimensions=health_dims,
            ),
            activity_heatmap=activity.heatmap,
            weekly_summary=weekly,
            skill_events=skill_snapshot.events,
            cost_summary=cost_summary,
            skill_trends=skill_trends,
        )

        return success_response(data=dashboard.model_dump())
    except Exception as e:
        raise internal_error(operation="Get growth dashboard", exception=e) from e
