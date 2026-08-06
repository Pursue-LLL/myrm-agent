"""Model-specific session usage listing for statistics API.

[INPUT]
- app.database.models Chat, Message (POS: ORM models)

[OUTPUT]
- router: GET /usage/model-sessions endpoint

[POS]
Split from session_analytics.py to satisfy file line budget.
"""

from __future__ import annotations

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


@router.get("/usage/model-sessions")
async def get_model_sessions(
    model: str = Query(
        ..., description="The full model identifier, e.g., 'openai/gpt-4o'"
    ),
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

        stmt = select(Message.chat_id, Message.extra_data, Message.created_at).where(
            and_(*filters)
        )
        result = await db.execute(stmt)
        rows = result.all()

        session_aggregates: dict[str, dict[str, object]] = {}
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

            if chat_id not in session_aggregates:
                session_aggregates[chat_id] = {
                    "calls": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cachedTokens": 0,
                    "totalTokens": 0,
                    "costUsd": 0.0,
                    "last_used_at": created_at,
                }

            agg = session_aggregates[chat_id]
            agg["calls"] = int(agg["calls"]) + 1
            agg["inputTokens"] = int(agg["inputTokens"]) + int(
                model_data.get("prompt_tokens") or 0
            )
            agg["outputTokens"] = int(agg["outputTokens"]) + int(
                model_data.get("completion_tokens") or 0
            )
            agg["cachedTokens"] = int(agg["cachedTokens"]) + int(
                model_data.get("cached_tokens") or 0
            )
            agg["totalTokens"] = int(agg["totalTokens"]) + int(
                model_data.get("total_tokens") or 0
            )

            cost_raw = model_data.get("cost_usd")
            if isinstance(cost_raw, (int, float)):
                agg["costUsd"] = float(agg["costUsd"]) + float(cost_raw)

            if created_at and (
                agg["last_used_at"] is None or created_at > agg["last_used_at"]
            ):
                agg["last_used_at"] = created_at

        if not session_aggregates:
            return success_response(data=[])

        chat_ids = list(session_aggregates.keys())
        chat_stmt = select(
            Chat.id, Chat.title, Chat.action_mode, Chat.created_at
        ).where(Chat.id.in_(chat_ids))
        chat_result = await db.execute(chat_stmt)
        chat_rows = chat_result.all()

        chat_details = {row.id: row for row in chat_rows}

        results = []
        for chat_id, agg in session_aggregates.items():
            chat_row = chat_details.get(chat_id)
            if not chat_row:
                continue

            results.append(
                {
                    "chatId": chat_id,
                    "title": chat_row.title or "Untitled",
                    "actionMode": chat_row.action_mode,
                    "createdAt": (
                        chat_row.created_at.isoformat() if chat_row.created_at else None
                    ),
                    "calls": agg["calls"],
                    "inputTokens": agg["inputTokens"],
                    "outputTokens": agg["outputTokens"],
                    "cachedTokens": agg["cachedTokens"],
                    "totalTokens": agg["totalTokens"],
                    "costUsd": round(float(agg["costUsd"]), 6),
                    "lastUsedAt": (
                        agg["last_used_at"].isoformat() if agg["last_used_at"] else None
                    ),
                }
            )

        results.sort(key=lambda x: x["totalTokens"], reverse=True)

        return success_response(data=results)
    except Exception as e:
        raise internal_error(
            operation="Get model-specific session statistics", exception=e
        ) from e
