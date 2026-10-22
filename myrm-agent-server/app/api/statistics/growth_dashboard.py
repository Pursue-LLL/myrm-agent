"""Growth Dashboard API — aggregated view of agent growth metrics.

[INPUT]
- app.api.statistics.skill_growth::(fetch_skill_evolution_data, fetch_skill_trends, fetch_skill_health) (POS: 技能侧看板数据域)
- app.database.connection::get_db (POS: 异步数据库会话依赖)

[OUTPUT]
- router: FastAPI 路由，提供 GET /statistics/growth-dashboard

[POS]
成长进化中心看板后端聚合 API。零新增存储，纯聚合内存/本地 SQLite 指标；技能侧数据（进化、趋势、健康）由 skill_growth 子包提供。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log import EventLogAnalytics
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.skill_growth import (
    SkillEvolutionEvent,
    SkillHealthItem,
    SkillTrendSeries,
    fetch_skill_evolution_data,
    fetch_skill_health,
    fetch_skill_trends,
)
from app.api.statistics.timezone_helper import resolve_user_timezone
from app.api.statistics.usage_aggregation import (
    DayAccumulator,
    TierAccumulator,
    compute_estimated_savings,
    extract_usage,
    normalize_tier,
)
from app.config.settings import settings
from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat, Message

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
    memory_citations_7d: int = 0


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


class CostSummary(BaseModel):
    """Aggregated cost/savings for the dashboard time range."""

    total_cost_usd: float = 0.0
    cache_savings_usd: float = 0.0
    routing_savings: float = 0.0
    routing_savings_percent: float = 0.0
    total_savings_usd: float = 0.0


class GrowthDashboardResponse(BaseModel):
    """Full dashboard payload — single GET returns everything."""

    snapshot: GrowthSnapshot
    activity_heatmap: list[ActivityDay]
    weekly_summary: WeeklySummary
    skill_events: list[SkillEvolutionEvent]
    cost_summary: CostSummary | None = None
    skill_trends: list[SkillTrendSeries] = Field(default_factory=list)
    skill_health: list[SkillHealthItem] = Field(default_factory=list)
    timezone: str = "UTC"


# ── Data fetchers (all read-only, no framework mutation) ─────────────


async def _fetch_memory_snapshot() -> tuple[dict[str, int], int, dict[str, float], int]:
    """Fetch memory counts by type via MemoryManager.

    Returns (by_type, health_score, dimensions, week_delta).
    """
    try:
        from app.core.memory.adapters.setup import (
            create_memory_manager,
            resolve_context_binding,
        )
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
                logger.debug(
                    "Failed to count %s memories for week delta: %s",
                    mem_type.value,
                    exc,
                )

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
    __slots__ = (
        "active_days",
        "max_streak",
        "heatmap",
        "tool_calls_this_week",
        "tool_calls_prev_week",
    )

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


async def _fetch_activity_data(
    time_range_days: int,
    tz_info: datetime.tzinfo | None = None,
    tz_name: str | None = None,
) -> _ActivitySnapshot:
    """Fetch activity metrics from EventLog including weekly tool_calls aggregation."""
    if not Path(settings.database.event_log_dir).exists():
        return _ActivitySnapshot()

    try:
        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)
        patterns = await analytics.get_global_activity_patterns(
            time_range_days=time_range_days,
            timezone=tz_name,
        )

        heatmap = [ActivityDay(date=act.date, count=act.session_count) for act in patterns.daily_activities]

        today = datetime.now(tz_info or UTC).date()
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


async def _fetch_memory_citations_7d(db: AsyncSession) -> int:
    """Count memory citations persisted on messages within the last 7 days."""
    try:
        week_start = datetime.now(UTC) - timedelta(days=7)
        stmt = (
            select(Message.extra_data)
            .where(
                Message.created_at >= week_start,
                Message.extra_data.isnot(None),
            )
            .limit(5000)
        )
        rows = (await db.execute(stmt)).scalars().all()
        total = 0
        for extra_data in rows:
            if not isinstance(extra_data, dict):
                continue
            cited = extra_data.get("citedMemoryIds")
            if cited is None:
                cited = extra_data.get("cited_memory_ids")
            if isinstance(cited, list):
                total += sum(1 for item in cited if isinstance(item, str) and item.strip())
        return total
    except Exception as e:
        logger.warning("Failed to fetch memory citations: %s", e)
        return 0


async def _fetch_cost_summary(db: AsyncSession, time_range_days: int) -> CostSummary | None:
    """Aggregate cost savings from message extra_data within the time range."""
    try:
        cutoff = datetime.now(UTC) - timedelta(days=time_range_days)
        stmt = (
            select(Message.extra_data)
            .where(
                and_(
                    Message.role == "assistant",
                    Message.created_at >= cutoff,
                    Message.extra_data.isnot(None),
                )
            )
            .order_by(Message.created_at.desc())
            .limit(10000)
        )
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
    timezone: str | None = Query(None, description="User local timezone, e.g. 'Asia/Shanghai'"),
    x_timezone: str | None = Header(None, alias="X-Timezone"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Aggregated growth dashboard — single endpoint, zero new storage.

    Combines: memory stats, activity heatmap, skill evolution, weekly summary.
    All data sources are read-only and already exist.
    """
    try:
        tz_info, tz_name = resolve_user_timezone(timezone, x_timezone)
        (
            (memory_by_type, health_score, health_dims, week_delta),
            activity,
            weekly,
            skill_snapshot,
            cost_summary,
            skill_trends,
            skill_health,
            memory_citations_7d,
        ) = await asyncio.gather(
            _fetch_memory_snapshot(),
            _fetch_activity_data(days, tz_info, tz_name),
            _fetch_weekly_summary(db),
            fetch_skill_evolution_data(),
            _fetch_cost_summary(db, days),
            fetch_skill_trends(days, tz_info),
            fetch_skill_health(),
            _fetch_memory_citations_7d(db),
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
                memory_citations_7d=memory_citations_7d,
            ),
            activity_heatmap=activity.heatmap,
            weekly_summary=weekly,
            skill_events=skill_snapshot.events,
            cost_summary=cost_summary,
            skill_trends=skill_trends,
            skill_health=skill_health,
            timezone=tz_name,
        )

        return success_response(data=dashboard.model_dump())
    except Exception as e:
        raise internal_error(operation="Get growth dashboard", exception=e) from e
