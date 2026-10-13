"""Model-specific session usage listing for statistics API.

[INPUT]
- app.database.models Chat, Message (POS: ORM models)

[OUTPUT]
- router: GET /usage/model-sessions endpoint

[POS]
Split from session_analytics.py to satisfy file line budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat, Message

router = APIRouter()


@dataclass(slots=True)
class _SessionUsage:
    """Running per-chat totals for one model."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    last_used_at: datetime | None = None


@router.get("/usage/model-sessions")
async def get_model_sessions(
    model: str = Query(..., description="The full model identifier, e.g., 'openai/gpt-4o'"),
    days: int = Query(30, ge=1, le=90, description="Lookback period in days"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get sessions that utilized a specific model, along with model-specific token/cost breakdown.

    Uses composite index on message creation time to narrow down messages before performing
    JSON extraction, ensuring robust O(log N) first-stage scanning.
    """
    try:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        filters = [
            Message.role == "assistant",
            Message.extra_data.isnot(None),
            Message.created_at >= start_dt,
        ]

        stmt = select(Message.chat_id, Message.extra_data, Message.created_at).where(and_(*filters))
        result = await db.execute(stmt)
        rows = result.all()

        session_aggregates: dict[str, _SessionUsage] = {}
        for chat_id, extra_data, created_at in rows:
            if not isinstance(extra_data, dict):
                continue
            usage = extra_data.get("usage")
            if not isinstance(usage, dict):
                continue
            model_usage = usage.get("model_usage")
            if not isinstance(model_usage, dict):
                continue

            model_data = model_usage.get(model)
            if not isinstance(model_data, dict):
                continue

            agg = session_aggregates.setdefault(chat_id, _SessionUsage())
            agg.calls += 1
            agg.input_tokens += int(model_data.get("prompt_tokens") or 0)
            agg.output_tokens += int(model_data.get("completion_tokens") or 0)
            agg.cached_tokens += int(model_data.get("cached_tokens") or 0)
            agg.total_tokens += int(model_data.get("total_tokens") or 0)

            cost_raw = model_data.get("cost_usd")
            if isinstance(cost_raw, (int, float)):
                agg.cost_usd += float(cost_raw)

            if created_at and (agg.last_used_at is None or created_at > agg.last_used_at):
                agg.last_used_at = created_at

        if not session_aggregates:
            return success_response(data=[])

        chat_ids = list(session_aggregates.keys())
        chat_stmt = select(Chat.id, Chat.title, Chat.action_mode, Chat.created_at).where(Chat.id.in_(chat_ids))
        chat_result = await db.execute(chat_stmt)
        chat_rows = chat_result.all()

        chat_details = {row.id: row for row in chat_rows}

        results: list[dict[str, str | int | float | None]] = []
        ranked = sorted(session_aggregates.items(), key=lambda item: item[1].total_tokens, reverse=True)
        for chat_id, agg in ranked:
            chat_row = chat_details.get(chat_id)
            if not chat_row:
                continue

            results.append(
                {
                    "chatId": chat_id,
                    "title": chat_row.title or "Untitled",
                    "actionMode": chat_row.action_mode,
                    "createdAt": (chat_row.created_at.isoformat() if chat_row.created_at else None),
                    "calls": agg.calls,
                    "inputTokens": agg.input_tokens,
                    "outputTokens": agg.output_tokens,
                    "cachedTokens": agg.cached_tokens,
                    "totalTokens": agg.total_tokens,
                    "costUsd": round(agg.cost_usd, 6),
                    "lastUsedAt": agg.last_used_at.isoformat() if agg.last_used_at else None,
                }
            )

        return success_response(data=results)
    except Exception as e:
        raise internal_error(operation="Get model-specific session statistics", exception=e) from e
