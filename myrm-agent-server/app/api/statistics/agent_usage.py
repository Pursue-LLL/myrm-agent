"""Per-Agent usage analytics endpoint.

[INPUT] database.models.chat::Chat, database.models.agent::Agent
[OUTPUT] GET /usage/by-agent — per-agent token/cost breakdown with 7-day sparkline
[POS] Agent-dimension usage aggregation for multi-agent cost transparency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
                func.sum(Chat.total_tokens).label("tokens"),
                func.sum(Chat.total_usd).label("usd"),
                func.sum(Chat.total_calls).label("calls"),
                func.count(Chat.id).label("sessions"),
            )
            .where(Chat.agent_id.isnot(None))
            .group_by(Chat.agent_id)
        )
        totals_result = await db.execute(totals_stmt)
        totals_rows = totals_result.all()

        if not totals_rows:
            return success_response(data={"agents": [], "total_agents": 0})

        agent_ids = [row.agent_id for row in totals_rows]
        grand_total_tokens = sum(row.tokens or 0 for row in totals_rows)
        grand_total_usd = sum(row.usd or 0.0 for row in totals_rows)

        agents_stmt = select(Agent.id, Agent.name, Agent.avatar).where(Agent.id.in_(agent_ids))
        agents_result = await db.execute(agents_stmt)
        agent_map: dict[str, tuple[str, str | None]] = {
            row.id: (row.name, row.avatar) for row in agents_result.all()
        }

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
        for row in sorted(totals_rows, key=lambda r: r.usd or 0, reverse=True):
            agent_id = row.agent_id
            name, avatar = agent_map.get(agent_id, (agent_id, None))
            tokens = row.tokens or 0
            usd = row.usd or 0.0
            percent_tokens = (tokens / grand_total_tokens * 100) if grand_total_tokens > 0 else 0
            percent_usd = (usd / grand_total_usd * 100) if grand_total_usd > 0 else 0

            sparkline = []
            agent_daily = daily_map.get(agent_id, {})
            for i in range(days):
                day_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
                day_data = agent_daily.get(day_str, {"tokens": 0, "usd": 0.0})
                sparkline.append({"date": day_str, **day_data})

            agents_data.append({
                "agentId": agent_id,
                "name": name,
                "avatar": avatar,
                "totalTokens": tokens,
                "totalUsd": round(usd, 6),
                "totalCalls": row.calls or 0,
                "sessions": row.sessions or 0,
                "percentTokens": round(percent_tokens, 1),
                "percentUsd": round(percent_usd, 1),
                "sparkline": sparkline,
            })

        return success_response(data={
            "agents": agents_data,
            "total_agents": len(agents_data),
            "grand_total_tokens": grand_total_tokens,
            "grand_total_usd": round(grand_total_usd, 6),
        })
    except Exception as e:
        raise internal_error(operation="Get per-agent usage analytics", exception=e) from e
