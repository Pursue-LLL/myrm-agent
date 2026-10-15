"""Model-sessions listing: per-chat totals, descending order by total tokens, and `lastUsedAt` (the newest message
that used the model, whatever the row order)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.statistics.session_model_sessions import get_model_sessions
from app.database import connection
from app.database.models import Chat, Message

pytestmark = pytest.mark.usefixtures("setup_test_database")

_MODEL = "openai/gpt-4o"
_USAGE: dict[str, object] = {
    "usage": {"model_usage": {_MODEL: {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}}
}


def _usage(prompt: int, completion: int, cached: int, total: int, cost_usd: float) -> dict[str, object]:
    entry = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "total_tokens": total,
        "cost_usd": cost_usd,
    }
    return {"usage": {"model_usage": {_MODEL: entry}}}


async def _seed_chat(created_ats: list[datetime], extra_data: dict[str, object] = _USAGE) -> str:
    """One chat with an assistant message per timestamp, inserted in the given order."""
    chat_id = str(uuid.uuid4())
    async with connection.get_session() as db:
        db.add(Chat(id=chat_id, title="Test", created_at=min(created_ats)))
        for index, created_at in enumerate(created_ats):
            db.add(
                Message(
                    id=f"{chat_id}-m{index}",
                    chat_id=chat_id,
                    role="assistant",
                    content="answer",
                    sent_at=created_at,
                    sent_timezone="UTC",
                    created_at=created_at,
                    extra_data=extra_data,
                )
            )
        await db.commit()
    return chat_id


async def _listing() -> list[dict[str, object]]:
    async with connection.get_session() as db:
        response = await get_model_sessions(model=_MODEL, days=30, db=db)
    sessions: list[dict[str, object]] = json.loads(bytes(response.body))["data"]
    return sessions


async def _listed_session(chat_id: str) -> dict[str, object]:
    return next(session for session in await _listing() if session["chatId"] == chat_id)


async def test_last_used_is_the_newest_message_even_when_it_is_not_the_last_row() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    newest = now - timedelta(hours=1)
    chat_id = await _seed_chat([now - timedelta(hours=2), newest, now - timedelta(hours=3)])

    session = await _listed_session(chat_id)

    assert session["calls"] == 3
    last_used_at = datetime.fromisoformat(str(session["lastUsedAt"])).replace(tzinfo=timezone.utc)
    assert last_used_at == newest


async def test_totals_are_summed_per_chat_and_listed_by_total_tokens_descending() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    small = await _seed_chat([now - timedelta(hours=1)], _usage(10, 5, 2, 15, 0.001))
    large = await _seed_chat([now - timedelta(hours=2), now - timedelta(hours=3)], _usage(100, 50, 20, 150, 0.01))

    listing = await _listing()

    chat_ids = [session["chatId"] for session in listing]
    assert chat_ids.index(large) < chat_ids.index(small)
    large_row = next(session for session in listing if session["chatId"] == large)
    assert (
        large_row["calls"],
        large_row["inputTokens"],
        large_row["outputTokens"],
        large_row["cachedTokens"],
        large_row["totalTokens"],
    ) == (2, 200, 100, 40, 300)
    assert large_row["costUsd"] == pytest.approx(0.02)
    small_row = next(session for session in listing if session["chatId"] == small)
    assert (small_row["calls"], small_row["totalTokens"]) == (1, 15)
    assert small_row["costUsd"] == pytest.approx(0.001)
