"""Chat usage cache is synced from assistant message extra_data snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat
from app.services.chat.chat_message import _chat_usage_cache
from app.services.chat.chat_service import ChatService


def _token_economics(call_count: int, tokens: int, cost_usd: float) -> dict[str, object]:
    return {
        "tokenEconomics": {
            "call_count": call_count,
            "total_cost_usd": cost_usd,
            "usage": {"total_tokens": tokens},
        }
    }


@pytest.mark.asyncio
async def test_persist_assistant_message_syncs_chat_usage_from_messages(
    db_session: AsyncSession,
) -> None:
    chat_id = "chat-usage-sync-e2e"
    _chat_usage_cache.invalidate(chat_id)
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="translate this",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id="msg-user-usage-e2e",
    )
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="first answer",
        extra_data=_token_economics(call_count=5, tokens=6000, cost_usd=0.2),
    )
    _chat_usage_cache.invalidate(chat_id)
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="second answer",
        extra_data=_token_economics(call_count=3, tokens=1200, cost_usd=0.15),
    )

    await db_session.rollback()
    chat = await db_session.scalar(select(Chat).where(Chat.id == chat_id))
    assert chat is not None
    assert chat.total_calls == 8
    assert chat.total_tokens == 7200
    assert abs(chat.total_usd - 0.35) < 1e-6


@pytest.mark.asyncio
async def test_usage_sync_reuses_ttl_cache_within_window(db_session: AsyncSession) -> None:
    chat_id = "chat-usage-ttl-cache"
    _chat_usage_cache.invalidate(chat_id)

    first = {"total_calls": 2, "total_tokens": 1000, "total_usd": 0.05}
    _chat_usage_cache.set(chat_id, first)

    with (
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_assistant_extra_data",
            return_value=[],
        ) as get_extras,
        patch(
            "app.database.repositories.chat_repo.ChatRepository.update_chat_fields",
            return_value=None,
        ) as update_fields,
    ):
        # First sync misses the TTL cache only if it expired; seed value is fresh
        await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="turn one")
        # Second sync within the TTL window must reuse the cached aggregate
        await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="turn two")
        assert get_extras.call_count == 0
        # turn1 append + turn1 sync + turn2 append + turn2 sync (cached)
        assert update_fields.call_count == 4
        assert update_fields.call_args_list[3].args[1] == first

        # After invalidation the next sync recomputes from messages
        _chat_usage_cache.invalidate(chat_id)
        get_extras.return_value = [
            _token_economics(call_count=7, tokens=4200, cost_usd=0.5)
        ]
        await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="turn three")
        assert get_extras.call_count == 1
        assert update_fields.call_args_list[5].args[1] == {
            "total_calls": 7,
            "total_tokens": 4200,
            "total_usd": 0.5,
        }
