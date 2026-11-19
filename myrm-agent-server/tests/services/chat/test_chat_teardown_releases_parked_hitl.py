"""Deleting, clearing or rewriting a chat retires the card its parked run holds, so no timer resumes a conversation that is gone.

The card of an ``ask_question`` pause is not tied to a database row the teardown touches: the parked run's collector and the
timer armed for it live in memory. Every teardown path that ends or rewrites the conversation has to release them.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from app.services.chat import chat_disposal
from app.services.chat.session_continuity_service import invalidate_chat_checkpoint
from tests.services.chat.disposal_support import (
    CHAT_ID,
    install_spies,
    installed_checkpointer,
    point_event_log_at_scratch,
)
from tests.support.local_harness_continuity import patch_session_continuity_sync

FAST = 0.05


@pytest.fixture(autouse=True)
def _fresh_scheduler() -> Iterator[None]:
    ApprovalTimeoutScheduler.get().cancel_all()
    yield
    ApprovalTimeoutScheduler.get().cancel_all()


@pytest.fixture(autouse=True)
def _slow_collaborators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_spies(monkeypatch)
    point_event_log_at_scratch(tmp_path, monkeypatch)
    patch_session_continuity_sync(monkeypatch)


@pytest_asyncio.fixture
async def checkpointer() -> AsyncIterator[BaseCheckpointSaver[str]]:
    async with installed_checkpointer() as saver:
        yield saver


@pytest_asyncio.fixture
async def parked_with_timer() -> AsyncIterator[AsyncMock]:
    """The chat waits at a clarification card: its run is the chat's collector and a timer is armed for it."""
    fired = AsyncMock()
    ApprovalTimeoutScheduler.get().schedule(CHAT_ID, FAST, "deny", fired)
    parked = StreamContentCollector(chat_id=CHAT_ID)
    parked.feed_event({"type": "clarification_required", "messageId": "msg-1", "data": {}})
    yield fired
    parked.cleanup()


async def _assert_retired(fired: AsyncMock) -> None:
    await asyncio.sleep(FAST * 4)
    fired.assert_not_awaited()
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None
    assert ApprovalTimeoutScheduler.get().resolve_if_first(CHAT_ID) is False


@pytest.mark.asyncio
async def test_soft_delete_retires_the_parked_card(parked_with_timer: AsyncMock) -> None:
    await chat_disposal.clear_runtime_caches(CHAT_ID)

    await _assert_retired(parked_with_timer)


@pytest.mark.asyncio
async def test_clearing_the_conversation_retires_the_parked_card(
    parked_with_timer: AsyncMock, checkpointer: BaseCheckpointSaver[str]
) -> None:
    await chat_disposal.clear_conversation_state(CHAT_ID)

    await _assert_retired(parked_with_timer)


@pytest.mark.asyncio
async def test_permanent_delete_retires_the_parked_card(
    parked_with_timer: AsyncMock, checkpointer: BaseCheckpointSaver[str]
) -> None:
    await chat_disposal.dispose_permanently_deleted_chats([CHAT_ID])

    await _assert_retired(parked_with_timer)


@pytest.mark.asyncio
async def test_rewriting_the_history_retires_the_parked_card(
    parked_with_timer: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edit, retry, undo, truncate and rewind clear the checkpoint thread the card was parked in."""
    monkeypatch.setattr("app.platform_utils.get_checkpointer", lambda: MemorySaver())

    await invalidate_chat_checkpoint(CHAT_ID)

    await _assert_retired(parked_with_timer)


TEARDOWNS: dict[str, Callable[[str], Awaitable[object]]] = {
    "soft delete": chat_disposal.clear_runtime_caches,
    "clear": chat_disposal.clear_conversation_state,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("teardown", list(TEARDOWNS))
async def test_a_teardown_of_a_chat_that_waits_for_no_answer_claims_nothing(
    teardown: str, checkpointer: BaseCheckpointSaver[str]
) -> None:
    """Nothing is parked: the arbiter stays open, so the next run's pause is answerable."""
    chat_id = f"chat-idle-{uuid.uuid4().hex[:6]}"

    await TEARDOWNS[teardown](chat_id)

    assert ApprovalTimeoutScheduler.get().resolve_if_first(chat_id) is True
