"""Tests for compact_chat guard integration."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import Chat, Message
from app.services.chat.compact_service import _get_compaction_lock, compact_chat


def _make_messages(chat_id: str, count: int) -> list[Message]:
    now = datetime.now(UTC)
    messages: list[Message] = []
    for index in range(count):
        messages.append(
            Message(
                id=f"msg-{chat_id}-{index}",
                chat_id=chat_id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
                sent_at=now,
                sent_timezone="UTC",
                created_at=now,
            )
        )
    return messages


@pytest.fixture(autouse=True)
def _mock_hydrate_compression_streak():
    with patch(
        "app.services.chat.compact.compression_streak.hydrate_compression_streak_from_db",
        AsyncMock(return_value=0),
    ):
        yield


@pytest.mark.asyncio
async def test_compact_chat_skips_when_summarize_circuit_open() -> None:
    db = AsyncMock()

    with patch(
        "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open",
        return_value=True,
    ):
        result = await compact_chat(db, "chat-1")

    assert result.compacted is False
    assert result.reason == "summarize_circuit_open"


@pytest.mark.asyncio
async def test_compact_chat_skips_when_concurrent_compaction_in_progress() -> None:
    db = AsyncMock()
    chat_id = "chat-lock-test"
    lock = _get_compaction_lock(chat_id)
    await lock.acquire()
    try:
        result = await compact_chat(db, chat_id)
    finally:
        lock.release()

    assert result.compacted is False
    assert result.reason == "concurrent_compaction_in_progress"


@pytest.mark.asyncio
async def test_compact_chat_for_idle_stale_skips_when_no_compactable_messages() -> None:
    db = AsyncMock()
    chat = Chat(id="chat-empty-tail", compacted_summary='{"user_goal":"prior work"}')

    with (
        patch(
            "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open",
            return_value=False,
        ),
        patch(
            "app.services.chat.compact.service.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.service.load_compactable_messages",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.compact.service.guarded_compact_summarize",
            AsyncMock(),
        ) as mock_summarize,
    ):
        result = await compact_chat(db, "chat-empty-tail", for_idle_stale=True)

    assert result.compacted is False
    assert result.reason == "no_compactable_messages"
    mock_summarize.assert_not_called()


@pytest.mark.asyncio
async def test_compact_chat_for_idle_stale_compacts_five_messages() -> None:
    db = AsyncMock()
    chat_id = "chat-idle-five"
    chat = Chat(id=chat_id, compacted_summary=None)
    db_messages = _make_messages(chat_id, 5)
    summary = MagicMock()
    summary.to_json.return_value = '{"user_goal":"compressed"}'

    with (
        patch(
            "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open",
            return_value=False,
        ),
        patch(
            "app.services.chat.compact.service.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.service.load_compactable_messages",
            AsyncMock(return_value=db_messages),
        ),
        patch(
            "app.services.chat.compact.service.get_llm_for_user",
            AsyncMock(return_value=(MagicMock(), 128_000)),
        ),
        patch(
            "app.services.chat.compact.service.guarded_compact_summarize",
            AsyncMock(return_value=([], summary)),
        ),
        patch(
            "app.services.chat.compact.service.backup_context",
            AsyncMock(return_value="/tmp/backup.jsonl"),
        ),
        patch(
            "app.services.chat.compact.service.do_persist_to_db",
            AsyncMock(),
        ),
        patch(
            "app.services.chat.compact.service.get_token_count",
            return_value=100,
        ),
    ):
        result = await compact_chat(db, chat_id, for_idle_stale=True)

    assert result.compacted is True
    assert result.message_count == 5


@pytest.mark.asyncio
async def test_compact_chat_skips_when_anti_thrash_active() -> None:
    db = AsyncMock()
    chat_id = "chat-anti-thrash"
    chat = Chat(id=chat_id, compacted_summary=None)
    db_messages = _make_messages(chat_id, 8)

    with (
        patch(
            "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open",
            return_value=False,
        ),
        patch(
            "app.services.chat.compact.service.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.service.load_compactable_messages",
            AsyncMock(return_value=db_messages),
        ),
        patch(
            "app.services.chat.compact.service.get_llm_for_user",
            AsyncMock(return_value=(MagicMock(), 128_000)),
        ),
        patch(
            "myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard.should_block_automatic_compression",
            return_value=True,
        ),
        patch(
            "app.services.chat.compact.service.guarded_compact_summarize",
            AsyncMock(),
        ) as mock_summarize,
    ):
        result = await compact_chat(db, chat_id, for_idle_stale=True)

    assert result.compacted is False
    assert result.reason == "compression_anti_thrash_active"
    mock_summarize.assert_not_called()


@pytest.mark.asyncio
async def test_compact_chat_idle_stale_uses_request_tokens_for_anti_thrash() -> None:
    """Large request-level context must not be blocked when tail slice is small."""
    db = AsyncMock()
    chat_id = "chat-idle-request-tokens"
    chat = Chat(id=chat_id, compacted_summary='{"user_goal":"large prior summary"}')
    db_messages = _make_messages(chat_id, 3)
    summary = MagicMock()
    summary.to_json.return_value = '{"user_goal":"merged"}'

    from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
        ANTI_THRASHING_STREAK_LIMIT,
    )
    from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
        create_task_metrics,
    )

    metrics = create_task_metrics(chat_id)
    metrics.compression_ineffective_streak = ANTI_THRASHING_STREAK_LIMIT

    async def _hydrate_streak(_db: AsyncMock, cid: str) -> int:
        from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
            get_compression_streak_store,
        )

        get_compression_streak_store().set_streak(cid, ANTI_THRASHING_STREAK_LIMIT)
        return ANTI_THRASHING_STREAK_LIMIT

    with (
        patch(
            "app.services.chat.compact.compression_streak.hydrate_compression_streak_from_db",
            AsyncMock(side_effect=_hydrate_streak),
        ),
        patch(
            "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open",
            return_value=False,
        ),
        patch(
            "app.services.chat.compact.service.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.service.load_compactable_messages",
            AsyncMock(return_value=db_messages),
        ),
        patch(
            "app.services.chat.compact.service.get_llm_for_user",
            AsyncMock(return_value=(MagicMock(), 128_000)),
        ),
        patch(
            "myrm_agent_harness.utils.token_estimation.estimate_messages_tokens",
            return_value=5_000,
        ),
        patch(
            "app.services.chat.compact.service.guarded_compact_summarize",
            AsyncMock(return_value=([], summary)),
        ),
        patch(
            "app.services.chat.compact.service.backup_context",
            AsyncMock(return_value="/tmp/backup.jsonl"),
        ),
        patch(
            "app.services.chat.compact.service.do_persist_to_db",
            AsyncMock(),
        ),
        patch(
            "app.services.chat.compact.service.get_token_count",
            return_value=100,
        ),
    ):
        blocked_without_request = await compact_chat(db, chat_id, for_idle_stale=True)
        allowed_with_request = await compact_chat(
            db,
            chat_id,
            for_idle_stale=True,
            request_tokens_for_guard=120_000,
        )

    assert blocked_without_request.compacted is False
    assert blocked_without_request.reason == "compression_anti_thrash_active"
    assert allowed_with_request.compacted is True


@pytest.mark.asyncio
async def test_compact_chat_default_enforces_min_messages_for_five_messages() -> None:
    db = AsyncMock()
    chat_id = "chat-manual-five"
    chat = Chat(id=chat_id, compacted_summary=None)
    db_messages = _make_messages(chat_id, 5)

    with (
        patch(
            "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open",
            return_value=False,
        ),
        patch(
            "app.services.chat.compact.service.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.service.load_compactable_messages",
            AsyncMock(return_value=db_messages),
        ),
        patch(
            "app.services.chat.compact.service.guarded_compact_summarize",
            AsyncMock(),
        ) as mock_summarize,
    ):
        result = await compact_chat(db, chat_id)

    assert result.compacted is False
    assert result.reason == "too_few_messages (5 < 10)"
    mock_summarize.assert_not_called()
