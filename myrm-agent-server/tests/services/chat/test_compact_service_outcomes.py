"""What ``compact_chat`` counts and reports.

Who may pass the anti-thrash guard (a person asking, not an automatic attempt), how savings are measured when a
summary already exists, and the closed set of reasons that come back for a compaction that did not happen.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
    ANTI_THRASHING_STREAK_LIMIT,
)
from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
    InMemoryCompressionStreakStore,
    get_compression_streak_store,
    register_compression_streak_store,
)
from myrm_agent_harness.agent.context_management.tracking.task_metrics import clear_task_metrics

from app.database.models import Chat
from app.services.chat.compact_service import compact_chat
from tests.services.chat.compaction_support import make_messages

_SERVICE = "app.services.chat.compact.service"
_CIRCUIT = "myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard.is_summarize_circuit_open"
_TOKEN_ESTIMATE = "myrm_agent_harness.utils.token_estimation.estimate_messages_tokens"
_WINDOW = 128_000


@pytest.fixture(autouse=True)
def _no_streak_hydration() -> Iterator[None]:
    with patch(
        "app.services.chat.compact.compression_streak.hydrate_compression_streak_from_db",
        AsyncMock(return_value=0),
    ):
        yield


@pytest.fixture
def chat_id() -> Iterator[str]:
    """A chat id whose anti-thrash streak lives in this process only, so a test sets and reads it without a database."""
    chat = f"chat-outcome-{uuid4().hex}"
    register_compression_streak_store(InMemoryCompressionStreakStore())
    yield chat
    register_compression_streak_store(None)
    clear_task_metrics(chat)


@dataclass(frozen=True)
class _Collaborators:
    summarize: AsyncMock
    persist: AsyncMock
    cooldown: AsyncMock


def _stored_summary(tokens: int) -> str:
    """A summary the parser accepts, as long as ``tokens`` characters (the env below counts one token per character)."""
    frame = '{"user_goal":""}'
    return '{"user_goal":"' + "p" * (tokens - len(frame)) + '"}'


@contextmanager
def _compaction_env(
    chat: Chat | None,
    *,
    messages: int = 12,
    message_tokens: int = 10_000,
    summary_tokens: int = 2_000,
    summarize_error: Exception | None = None,
    persist_error: Exception | None = None,
) -> Iterator[_Collaborators]:
    """Stand in for everything around ``compact_chat``: the chat, its messages, the model, the token counts and the writes.

    Tokens are counted as characters, so the new summary and a stored one of the same length weigh the same.
    """
    summary = MagicMock()
    summary.to_json.return_value = "s" * summary_tokens
    collaborators = _Collaborators(
        summarize=AsyncMock(side_effect=summarize_error) if summarize_error else AsyncMock(return_value=([], summary)),
        persist=AsyncMock(side_effect=persist_error),
        cooldown=AsyncMock(),
    )
    replacements: dict[str, object] = {
        _CIRCUIT: MagicMock(return_value=False),
        _TOKEN_ESTIMATE: MagicMock(return_value=message_tokens),
        f"{_SERVICE}.load_chat": AsyncMock(return_value=chat),
        f"{_SERVICE}.load_compactable_messages": AsyncMock(return_value=make_messages("env", messages)),
        f"{_SERVICE}.get_llm_for_user": AsyncMock(return_value=(MagicMock(), _WINDOW)),
        f"{_SERVICE}.guarded_compact_summarize": collaborators.summarize,
        f"{_SERVICE}.backup_context": AsyncMock(return_value="/tmp/backup.jsonl"),
        f"{_SERVICE}.do_persist_to_db": collaborators.persist,
        f"{_SERVICE}.record_compaction_failure_cooldown": collaborators.cooldown,
        f"{_SERVICE}.get_token_count": len,
    }
    with ExitStack() as stack:
        for target, replacement in replacements.items():
            stack.enter_context(patch(target, replacement))
        yield collaborators


class TestExplicitRequest:
    """The guard stops automatic attempts; a person who asked for a compaction is not stopped by it."""

    async def test_a_request_compacts_through_an_ineffective_streak(self, chat_id: str) -> None:
        get_compression_streak_store().set_streak(chat_id, ANTI_THRASHING_STREAK_LIMIT)

        with _compaction_env(Chat(id=chat_id)) as env:
            automatic = await compact_chat(AsyncMock(), chat_id)
            assert env.summarize.await_count == 0
            requested = await compact_chat(AsyncMock(), chat_id, explicit_request=True)

        assert (automatic.compacted, automatic.reason) == (False, "compression_anti_thrash_active")
        assert requested.compacted is True
        env.summarize.assert_awaited_once()

    @pytest.mark.parametrize(
        ("streak_before", "summary_tokens", "streak_after"),
        [
            pytest.param(ANTI_THRASHING_STREAK_LIMIT, 2_000, 0, id="an-effective-compaction-clears-the-streak"),
            pytest.param(
                ANTI_THRASHING_STREAK_LIMIT - 1,
                9_500,
                ANTI_THRASHING_STREAK_LIMIT,
                id="an-ineffective-one-extends-it-up-to-the-limit",
            ),
            pytest.param(
                ANTI_THRASHING_STREAK_LIMIT,
                9_500,
                ANTI_THRASHING_STREAK_LIMIT,
                id="an-ineffective-one-does-not-pass-the-limit",
            ),
        ],
    )
    async def test_a_request_counts_toward_the_streak_up_to_the_guard_limit(
        self, chat_id: str, streak_before: int, summary_tokens: int, streak_after: int
    ) -> None:
        store = get_compression_streak_store()
        store.set_streak(chat_id, streak_before)

        with _compaction_env(Chat(id=chat_id), summary_tokens=summary_tokens):
            await compact_chat(AsyncMock(), chat_id, explicit_request=True)

        assert store.get_streak(chat_id) == streak_after

    async def test_repeated_requests_never_lift_the_streak_past_the_limit(self, chat_id: str) -> None:
        """A person retrying a compaction that saves little arms the guard, but cannot make the chat look stuck."""
        store = get_compression_streak_store()
        streaks: list[int] = []

        with _compaction_env(Chat(id=chat_id), summary_tokens=9_500):
            for _ in range(6):
                await compact_chat(AsyncMock(), chat_id, explicit_request=True)
                streaks.append(store.get_streak(chat_id))

        assert streaks == [min(attempt, ANTI_THRASHING_STREAK_LIMIT) for attempt in range(1, 7)]

    async def test_an_automatic_attempt_released_by_the_safety_net_keeps_counting(self, chat_id: str) -> None:
        """Past the limit only an automatic attempt on a context that is nearly full extends the streak: that is the stuck signal."""
        store = get_compression_streak_store()
        store.set_streak(chat_id, ANTI_THRASHING_STREAK_LIMIT)
        chat = Chat(id=chat_id, compacted_summary=_stored_summary(int(_WINDOW * 0.9) + 100))

        with _compaction_env(chat, messages=4, message_tokens=3_000, summary_tokens=118_000):
            result = await compact_chat(AsyncMock(), chat_id)

        assert result.compacted is True
        assert store.get_streak(chat_id) == ANTI_THRASHING_STREAK_LIMIT + 1


class TestSavingsMeasurement:
    """A compaction replaces the stored summary together with the messages after it, and is measured against both."""

    async def test_an_incremental_compaction_is_measured_against_the_summary_it_replaces(self, chat_id: str) -> None:
        chat = Chat(id=chat_id, compacted_summary=_stored_summary(2_500))

        with _compaction_env(chat, messages=4, message_tokens=3_000, summary_tokens=3_000) as env:
            result = await compact_chat(AsyncMock(), chat_id)

        assert (result.original_tokens, result.summary_tokens, result.tokens_saved) == (5_500, 3_000, 2_500)
        assert env.persist.await_args_list[0].kwargs["tokens_saved"] == 2_500
        assert get_compression_streak_store().get_streak(chat_id) == 0

    async def test_a_compaction_that_grows_the_context_reports_no_savings(self, chat_id: str) -> None:
        with _compaction_env(Chat(id=chat_id), message_tokens=1_000, summary_tokens=1_200) as env:
            result = await compact_chat(AsyncMock(), chat_id)

        assert result.compacted is True
        assert result.tokens_saved == 0
        assert env.persist.await_args_list[0].kwargs["tokens_saved"] == 0
        assert get_compression_streak_store().get_streak(chat_id) == 1

    async def test_the_safety_net_counts_the_stored_summary(self, chat_id: str) -> None:
        """A summary that alone fills 90% of the window is context the guard must see, however few messages follow it."""
        get_compression_streak_store().set_streak(chat_id, ANTI_THRASHING_STREAK_LIMIT)
        chat = Chat(id=chat_id, compacted_summary=_stored_summary(int(_WINDOW * 0.9) + 100))

        with _compaction_env(chat, messages=4, message_tokens=3_000, summary_tokens=100_000):
            result = await compact_chat(AsyncMock(), chat_id)

        assert result.compacted is True


class TestReasons:
    """What comes back for a compaction that did not happen is a bare code; the detail goes to the log."""

    async def test_a_missing_chat_is_reported_as_such(self, chat_id: str) -> None:
        with _compaction_env(None):
            result = await compact_chat(AsyncMock(), chat_id)

        assert (result.compacted, result.reason) == (False, "chat_not_found")

    async def test_too_few_messages_is_reported_without_its_counts_and_logs_them(
        self, chat_id: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=_SERVICE), _compaction_env(Chat(id=chat_id), messages=5):
            result = await compact_chat(AsyncMock(), chat_id)

        assert (result.compacted, result.reason, result.message_count) == (False, "too_few_messages", 5)
        assert "5 messages, 10 needed" in caplog.text

    async def test_a_timeout_is_reported_without_its_detail_and_starts_the_cooldown(self, chat_id: str) -> None:
        db = AsyncMock()

        with _compaction_env(Chat(id=chat_id), summarize_error=asyncio.TimeoutError("summarize exceeded 90s")) as env:
            result = await compact_chat(db, chat_id)

        assert (result.compacted, result.reason) == (False, "timeout")
        env.cooldown.assert_awaited_once_with(db, chat_id, "timeout: summarize exceeded 90s")

    async def test_a_failed_save_is_reported_without_its_detail_and_starts_the_cooldown(self, chat_id: str) -> None:
        db = AsyncMock()

        with _compaction_env(Chat(id=chat_id), persist_error=ValueError("Cannot resolve before_message_id")) as env:
            result = await compact_chat(db, chat_id)

        assert (result.compacted, result.reason) == (False, "persist_failed")
        db.rollback.assert_awaited_once()
        env.cooldown.assert_awaited_once_with(db, chat_id, "persist_failed: Cannot resolve before_message_id")
