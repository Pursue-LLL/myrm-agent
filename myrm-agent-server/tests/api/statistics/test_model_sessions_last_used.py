"""`lastUsedAt` in the model-sessions listing is the newest message that used the model, whatever the row order."""

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
_USAGE = {"usage": {"model_usage": {_MODEL: {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}}}


async def _seed_chat(created_ats: list[datetime]) -> str:
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
                    extra_data=_USAGE,
                )
            )
        await db.commit()
    return chat_id


async def _listed_session(chat_id: str) -> dict[str, object]:
    async with connection.get_session() as db:
        response = await get_model_sessions(model=_MODEL, days=30, db=db)
    sessions = json.loads(bytes(response.body))["data"]
    return next(session for session in sessions if session["chatId"] == chat_id)


async def test_last_used_is_the_newest_message_even_when_it_is_not_the_last_row() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    newest = now - timedelta(hours=1)
    chat_id = await _seed_chat([now - timedelta(hours=2), newest, now - timedelta(hours=3)])

    session = await _listed_session(chat_id)

    assert session["calls"] == 3
    last_used_at = datetime.fromisoformat(str(session["lastUsedAt"])).replace(tzinfo=timezone.utc)
    assert last_used_at == newest
