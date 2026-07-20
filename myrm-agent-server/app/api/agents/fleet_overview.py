"""Agent Fleet Overview — aggregated per-agent statistics for the /agents page.

[INPUT]
@database.models.chat::Chat (agent_id, total_tokens, total_usd, total_calls)
@database.models.cron::CronJobModel (agent_id, status)
@database.models.approval::ApprovalRecord (agent_id, status)
@services.agent.gateway::AgentGateway (active sessions with agent_id)

[OUTPUT]
GET /api/v1/agents/fleet-overview — per-agent stats + global KPI summary

[POS]
Fleet 聚合视图 API。从现有 Chat/CronJob/Approval 表和 Gateway 内存数据中
按 agent_id 聚合统计信息，供前端 /agents 页面 KPI 卡片和增强 Agent 卡片使用。
零新表，纯读聚合。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat
from app.database.models.approval import ApprovalRecord
from app.database.models.cron import CronJobModel
from app.services.agent.gateway import get_agent_gateway

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/fleet-overview")
async def fleet_overview(db: AsyncSession = Depends(get_db)) -> dict:
    """Per-agent aggregated statistics for the Fleet view.

    Returns:
        - kpi: Global KPI summary (online agents, monthly tokens/cost, pending approvals)
        - agents: Dict keyed by agent_id with per-agent stats
    """
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 1. Monthly usage per agent (from Chat table)
    usage_stmt = (
        select(
            Chat.agent_id,
            func.count(Chat.id).label("session_count"),
            func.coalesce(func.sum(Chat.total_tokens), 0).label("month_tokens"),
            func.coalesce(func.sum(Chat.total_usd), 0).label("month_cost"),
        )
        .where(
            and_(
                Chat.created_at >= month_start,
                Chat.deleted_at.is_(None),
            )
        )
        .group_by(Chat.agent_id)
    )
    usage_rows = (await db.execute(usage_stmt)).all()

    agent_stats: dict[str, dict[str, object]] = {}
    for row in usage_rows:
        aid = row.agent_id or "default"
        agent_stats[aid] = {
            "sessionCount": row.session_count,
            "monthTokens": int(row.month_tokens),
            "monthCost": round(float(row.month_cost), 4),
        }

    # 2. Active cron jobs per agent
    cron_stmt = (
        select(
            CronJobModel.agent_id,
            func.count(CronJobModel.id).label("cron_count"),
        )
        .where(
            and_(
                CronJobModel.agent_id.isnot(None),
                CronJobModel.status == "active",
            )
        )
        .group_by(CronJobModel.agent_id)
    )
    cron_rows = (await db.execute(cron_stmt)).all()

    for row in cron_rows:
        aid = row.agent_id or "default"
        agent_stats.setdefault(aid, _empty_stats())
        agent_stats[aid]["cronCount"] = row.cron_count

    # 3. Pending approvals per agent
    approval_stmt = (
        select(
            ApprovalRecord.agent_id,
            func.count(ApprovalRecord.id).label("pending_count"),
        )
        .where(ApprovalRecord.status == "PENDING")
        .group_by(ApprovalRecord.agent_id)
    )
    approval_rows = (await db.execute(approval_stmt)).all()

    for row in approval_rows:
        aid = row.agent_id or "default"
        agent_stats.setdefault(aid, _empty_stats())
        agent_stats[aid]["pendingApprovals"] = row.pending_count

    # 4. Real-time status from Gateway
    gateway = get_agent_gateway()
    active_sessions = gateway.get_active_sessions()
    active_agent_ids: set[str] = set()

    for session in active_sessions:
        aid = session.get("agentId")
        if isinstance(aid, str) and aid:
            active_agent_ids.add(aid)
            agent_stats.setdefault(aid, _empty_stats())
            agent_stats[aid]["status"] = "busy"

    # Fill defaults
    for _aid, stats in agent_stats.items():
        stats.setdefault("sessionCount", 0)
        stats.setdefault("monthTokens", 0)
        stats.setdefault("monthCost", 0.0)
        stats.setdefault("cronCount", 0)
        stats.setdefault("pendingApprovals", 0)
        stats.setdefault("status", "idle")

    # Build global KPI
    total_month_tokens = sum(int(s.get("monthTokens", 0)) for s in agent_stats.values())
    total_month_cost = sum(float(s.get("monthCost", 0)) for s in agent_stats.values())
    total_pending = sum(int(s.get("pendingApprovals", 0)) for s in agent_stats.values())

    kpi = {
        "onlineAgents": len(active_agent_ids),
        "monthTokens": total_month_tokens,
        "monthCost": round(total_month_cost, 4),
        "pendingApprovals": total_pending,
    }

    return success_response({"kpi": kpi, "agents": agent_stats})


def _empty_stats() -> dict[str, object]:
    return {
        "sessionCount": 0,
        "monthTokens": 0,
        "monthCost": 0.0,
        "cronCount": 0,
        "pendingApprovals": 0,
        "status": "idle",
    }
