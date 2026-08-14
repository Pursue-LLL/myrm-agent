"""Mutations (regenerate / sibling switch) rebuild the Chat usage cache."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.services.chat.chat_message import _chat_usage_cache
from app.services.chat.chat_service import ChatService


@pytest.fixture(autouse=True)
def _mock_checkpoint_sync():
    """Checkpoint sync is not under test here — mock it to avoid RuntimeError."""
    with patch(
        "app.services.chat.chat_turn._ChatTurnMixin._sync_checkpoint_after_mutation",
        new_callable=AsyncMock,
    ):
        yield


def _token_economics(call_count: int, tokens: int, cost_usd: float) -> dict[str, object]:
    return {
        "tokenEconomics": {
            "call_count": call_count,
            "total_cost_usd": cost_usd,
            "usage": {"total_tokens": tokens},
        }
    }


async def _seed(chat_id: str) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="first query",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id="msg-u1",
    )
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="answer one",
        extra_data=_token_economics(5, 6000, 0.2),
    )
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="second query",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id="msg-u2",
    )
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="answer two",
        extra_data=_token_economics(3, 1200, 0.15),
    )


async def _assistant_message_id(db: AsyncSession, chat_id: str, content: str) -> str:
    row = await db.execute(
        select(Message.id).where(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.content == content,
        )
    )
    return row.scalar_one()


async def _chat_usage(db: AsyncSession, chat_id: str) -> tuple[int, int, float]:
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id))
    assert chat is not None
    return chat.total_calls, chat.total_tokens, chat.total_usd


@pytest.mark.asyncio
async def test_regenerate_drops_inactive_sibling_usage(db_session: AsyncSession) -> None:
    """Regenerating deactivates the last response so its usage leaves the cache."""
    chat_id = "chat-usage-regenerate"
    _chat_usage_cache.invalidate(chat_id)
    await _seed(chat_id)

    await db_session.rollback()
    assert await _chat_usage(db_session, chat_id) == (8, 7200, 0.35)

    result = await ChatService.regenerate_last_turn(chat_id)
    assert result.success is True

    await db_session.rollback()
    calls, tokens, usd = await _chat_usage(db_session, chat_id)
    assert (calls, tokens) == (5, 6000)
    assert abs(usd - 0.2) < 1e-6


@pytest.mark.asyncio
async def test_switch_sibling_rebuilds_usage_for_active_sibling(db_session: AsyncSession) -> None:
    """Switching the active sibling re-aggregates from the new active set."""
    chat_id = "chat-usage-switch-sibling"
    _chat_usage_cache.invalidate(chat_id)
    await _seed(chat_id)

    result = await ChatService.regenerate_last_turn(chat_id)
    assert result.success is True

    await db_session.rollback()
    second_id = await _assistant_message_id(db_session, chat_id, "answer two")

    ok = await ChatService.switch_sibling(chat_id, result.sibling_group_id, second_id)
    assert ok is True

    await db_session.rollback()
    calls, tokens, usd = await _chat_usage(db_session, chat_id)
    assert (calls, tokens) == (8, 7200)
    assert abs(usd - 0.35) < 1e-6
