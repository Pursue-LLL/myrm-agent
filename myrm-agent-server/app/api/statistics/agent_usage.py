"""Per-Agent usage analytics endpoint.

[INPUT] database.models.chat::Chat, database.models.agent::Agent
[OUTPUT] GET /usage/by-agent — per-agent token/cost breakdown with 7-day sparkline
[POS] Agent-dimension usage aggregation for multi-agent cost transparency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat
from app.database.models.agent import Agent

router = APIRouter()


@router.get("/usage/by-agent")
async def get_usage_by_agent(
    days: int = Query(7, ge=1, le=90, description="Days for sparkline trend data"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Per-agent token usage breakdown with daily sparkline.

    Returns each agent's total tokens, cost, calls, percentage share,
    and a daily trend array for the sparkline visualization.
    """
    try:
        totals_stmt = (
            select(
                Chat.agent_id,
                Chat.source,
                (Chat.ephemeral_subagents.isnot(None)).label("has_subagents"),
                func.sum(Chat.total_tokens).label("tokens"),
                func.sum(Chat.total_usd).label("usd"),
                func.sum(Chat.total_calls).label("calls"),
                func.count(Chat.id).label("sessions"),
            )
            .where(Chat.agent_id.isnot(None))
            .group_by(Chat.agent_id, Chat.source, Chat.ephemeral_subagents.isnot(None))
        )
        totals_result = await db.execute(totals_stmt)
        totals_rows = totals_result.all()

        if not totals_rows:
            return success_response(data={"agents": [], "total_agents": 0})

        agent_agg: dict[str, dict[str, Any]] = {}
        for row in totals_rows:
            aid = row.agent_id
            tokens = getattr(row, "tokens", 0) or 0
            usd = getattr(row, "usd", 0.0) or 0.0
            calls = getattr(row, "calls", 0) or 0
            sessions = getattr(row, "sessions", 0) or 0
            source = str(getattr(row, "source", "web") or "web").lower()
            has_subagents = bool(getattr(row, "has_subagents", False))

            if aid not in agent_agg:
                agent_agg[aid] = {
                    "tokens": 0,
                    "usd": 0.0,
                    "calls": 0,
                    "sessions": 0,
                    "web_usd": 0.0,
                    "cron_usd": 0.0,
                    "channel_usd": 0.0,
                    "subagents_usd": 0.0,
                    "web_tokens": 0,
                    "cron_tokens": 0,
                    "channel_tokens": 0,
                    "subagents_tokens": 0,
                }

            item = agent_agg[aid]
            item["tokens"] += tokens
            item["usd"] += usd
            item["calls"] += calls
            item["sessions"] += sessions

            if has_subagents:
                item["subagents_usd"] += usd
                item["subagents_tokens"] += tokens
            elif source == "cron":
                item["cron_usd"] += usd
                item["cron_tokens"] += tokens
            elif source in ("channel", "discord", "slack", "telegram", "feishu", "dingtalk", "wechat") or source.startswith("channel"):
                item["channel_usd"] += usd
                item["channel_tokens"] += tokens
            else:
                item["web_usd"] += usd
                item["web_tokens"] += tokens

        agent_ids = list(agent_agg.keys())
        grand_total_tokens = sum(item["tokens"] for item in agent_agg.values())
        grand_total_usd = sum(item["usd"] for item in agent_agg.values())

        agents_stmt = select(Agent.id, Agent.name, Agent.avatar).where(Agent.id.in_(agent_ids))
        agents_result = await db.execute(agents_stmt)
        agent_map: dict[str, tuple[str, str | None]] = {row.id: (row.name, row.avatar) for row in agents_result.all()}

        start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        daily_stmt = (
            select(
                Chat.agent_id,
                func.date(Chat.created_at).label("day"),
                func.sum(Chat.total_tokens).label("tokens"),
                func.sum(Chat.total_usd).label("usd"),
            )
            .where(Chat.agent_id.isnot(None), Chat.created_at >= start_dt)
            .group_by(Chat.agent_id, func.date(Chat.created_at))
        )
        daily_result = await db.execute(daily_stmt)
        daily_map: dict[str, dict[str, dict[str, float]]] = {}
        for row in daily_result.all():
            daily_map.setdefault(row.agent_id, {})[str(row.day)] = {
                "tokens": row.tokens or 0,
                "usd": round(row.usd or 0.0, 6),
            }

        agents_data = []
        for aid, item in sorted(agent_agg.items(), key=lambda pair: pair[1]["usd"], reverse=True):
            name, avatar = agent_map.get(aid, (aid, None))
            tokens = item["tokens"]
            usd = item["usd"]
            percent_tokens = (tokens / grand_total_tokens * 100) if grand_total_tokens > 0 else 0
            percent_usd = (usd / grand_total_usd * 100) if grand_total_usd > 0 else 0

            sparkline = []
            agent_daily = daily_map.get(aid, {})
            for i in range(days):
                day_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
                day_data = agent_daily.get(day_str, {"tokens": 0, "usd": 0.0})
                sparkline.append({"date": day_str, **day_data})

            attribution = {
                "webUsd": round(item["web_usd"], 6),
                "cronUsd": round(item["cron_usd"], 6),
                "channelUsd": round(item["channel_usd"], 6),
                "subagentsUsd": round(item["subagents_usd"], 6),
                "webTokens": item["web_tokens"],
                "cronTokens": item["cron_tokens"],
                "channelTokens": item["channel_tokens"],
                "subagentsTokens": item["subagents_tokens"],
            }

            agents_data.append(
                {
                    "agentId": aid,
                    "name": name,
                    "avatar": avatar,
                    "totalTokens": tokens,
                    "totalUsd": round(usd, 6),
                    "totalCalls": item["calls"],
                    "sessions": item["sessions"],
                    "percentTokens": round(percent_tokens, 1),
                    "percentUsd": round(percent_usd, 1),
                    "sparkline": sparkline,
                    "attribution": attribution,
                }
            )

        return success_response(
            data={
                "agents": agents_data,
                "total_agents": len(agents_data),
                "grand_total_tokens": grand_total_tokens,
                "grand_total_usd": round(grand_total_usd, 6),
            }
        )
    except Exception as e:
        raise internal_error(operation="Get per-agent usage analytics", exception=e) from e
