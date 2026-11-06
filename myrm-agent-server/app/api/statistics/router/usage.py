"""[INPUT]
- .common (POS: shared router)

[OUTPUT]
- _parse_date, get_usage_statistics, get_usage_radar, get_daily_usage, get_session_usage

[POS]
Statistics endpoints: usage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from fastapi import Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.timezone_helper import resolve_user_timezone, to_user_local_dt
from app.api.statistics.usage_aggregation import DayAccumulator, aggregate_usage, extract_usage, normalize_usage_rows
from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat, Message

from .common import router


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


@router.get("/usage/daily")
async def get_daily_usage(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    timezone: str | None = Query(None, description="User local timezone, e.g. 'Asia/Shanghai'"),
    x_timezone: str | None = Header(None, alias="X-Timezone"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get daily aggregated token usage for charting.

    Returns an array of daily usage summaries for the specified lookback period,
    bucketed by the user's local timezone.
    """
    try:
        from datetime import timedelta

        tz_info, tz_name = resolve_user_timezone(timezone, x_timezone)

        end_dt = datetime.now(tz_info)
        start_dt = end_dt - timedelta(days=days)
        start_dt_utc = start_dt.astimezone(UTC)

        stmt = (
            select(Message.extra_data, Message.created_at)
            .where(
                and_(
                    Message.chat_id == Chat.id,
                    Message.role == "assistant",
                    Message.extra_data.isnot(None),
                    Message.created_at >= start_dt_utc,
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

            local_dt = to_user_local_dt(created_at, tz_info)
            day_key = local_dt.strftime("%Y-%m-%d") if local_dt else created_at.strftime("%Y-%m-%d")
            if day_key not in daily_map:
                daily_map[day_key] = DayAccumulator()
            daily_map[day_key].add(usage, extra_data)

        daily_list = [{"date": day, **acc.to_dict()} for day, acc in sorted(daily_map.items())]

        return success_response(
            data={
                "days": days,
                "timezone": tz_name,
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
