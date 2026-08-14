"""Chat usage cache is synced from assistant message extra_data snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat
from app.services.chat.chat_service import ChatService
from app.services.chat.chat_usage_sync import _chat_usage_cache, sync_chat_usage


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


async def _seed_user_message(chat_id: str, content: str, message_id: str) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content=content,
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id=message_id,
    )


@pytest.mark.asyncio
async def test_persist_assistant_message_syncs_chat_usage_from_messages(
    db_session: AsyncSession,
) -> None:
    """Consecutive turns within the TTL window still accumulate exact totals.

    The cache is keyed on the last message id, so a new turn invalidates the
    cached aggregate and the rebuilt value covers every persisted message.
    """
    chat_id = "chat-usage-sync-e2e"
    _chat_usage_cache.invalidate(chat_id)
    await _seed_user_message(chat_id, "translate this", "msg-user-usage-e2e")
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="first answer",
        extra_data=_token_economics(call_count=5, tokens=6000, cost_usd=0.2),
    )
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
async def test_usage_sync_skips_aggregate_when_cache_fresh_and_rebuilds_on_new_message(
    db_session: AsyncSession,
) -> None:
    chat_id = "chat-usage-ttl-cache"
    _chat_usage_cache.invalidate(chat_id)

    first = {"total_calls": 2, "total_tokens": 1000, "total_usd": 0.05}
    _chat_usage_cache.set(chat_id, "msg-1", first)

    with (
        patch(
            "app.database.repositories.chat_repo.ChatRepository.get_assistant_extra_data",
            return_value=([], "msg-1"),
        ) as get_extras,
        patch(
            "app.database.repositories.chat_repo.ChatRepository.update_chat_fields",
            return_value=None,
        ) as update_fields,
        patch(
            "app.services.statistics.usage_aggregation.aggregate_chat_usage_rows",
            return_value=first,
        ) as aggregate,
    ):
        await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="turn one")
        await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="turn two")
        # Cache covers the same last message id -> reuse aggregate, no recompute
        assert aggregate.call_count == 0
        assert update_fields.call_count == 4
        assert update_fields.call_args_list[3].args[2] == first

        # A new last message id invalidates the cache -> rebuild from messages
        get_extras.return_value = ([_token_economics(7, 4200, 0.5)], "msg-2")
        aggregate.return_value = {"total_calls": 7, "total_tokens": 4200, "total_usd": 0.5}
        await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="turn three")
        assert aggregate.call_count == 1
        assert update_fields.call_args_list[5].args[2] == {
            "total_calls": 7,
            "total_tokens": 4200,
            "total_usd": 0.5,
        }


@pytest.mark.asyncio
async def test_undo_last_turn_rebuilds_chat_usage(db_session: AsyncSession) -> None:
    """Undoing a turn drops the removed message usage from the Chat cache."""
    chat_id = "chat-usage-undo-e2e"
    _chat_usage_cache.invalidate(chat_id)
    await _seed_user_message(chat_id, "first query", "msg-u1")
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="answer one",
        extra_data=_token_economics(call_count=5, tokens=6000, cost_usd=0.2),
    )
    await _seed_user_message(chat_id, "second query", "msg-u2")
    await ChatService.persist_assistant_message_safe(
        chat_id=chat_id,
        content="answer two",
        extra_data=_token_economics(call_count=3, tokens=1200, cost_usd=0.15),
    )

    await db_session.rollback()
    chat = await db_session.scalar(select(Chat).where(Chat.id == chat_id))
    assert chat is not None
    assert chat.total_calls == 8
    assert chat.total_tokens == 7200

    result = await ChatService.undo_last_turn(chat_id)
    assert result.success is True
    assert result.deleted_count == 2

    await db_session.rollback()
    chat = await db_session.scalar(select(Chat).where(Chat.id == chat_id))
    assert chat is not None
    assert chat.total_calls == 5
    assert chat.total_tokens == 6000
    assert abs(chat.total_usd - 0.2) < 1e-6


@pytest.mark.asyncio
async def test_sync_chat_usage_rejects_unsafe_chat_id_before_db_access() -> None:
    """An unsafe chat_id must short-circuit before any repository call."""
    with patch("app.database.repositories.chat_repo.ChatRepository.get_assistant_extra_data") as mock_ge:
        await sync_chat_usage("chat/../../etc/passwd")
    mock_ge.assert_not_called()


@pytest.mark.asyncio
async def test_sync_chat_usage_swallows_repository_errors() -> None:
    """A failed aggregation must be logged and never propagate to the caller."""
    mock_repo = AsyncMock()
    mock_repo.get_assistant_extra_data.side_effect = RuntimeError("db boom")
    mock_uow = AsyncMock()
    mock_uow.__aenter__.return_value = mock_uow
    with (
        patch("app.services.chat.chat_usage_sync.UnitOfWork", return_value=mock_uow),
        patch(
            "app.services.chat.chat_usage_sync._ChatServiceBase._cr",
            return_value=mock_repo,
        ) as mock_cr,
    ):
        await sync_chat_usage("safe-chat-id")
    mock_cr.assert_called()
