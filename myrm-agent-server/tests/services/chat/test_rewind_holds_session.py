"""A rewind holds the chat's gateway session from its first step to its last.

Between the file revert and the message deletion, a turn that started would have its fresh messages deleted together
with the rewound ones. Holding the session makes every turn entry refuse instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.gateway import AgentBusyError, AgentGateway
from app.services.chat.chat_service import ChatService
from app.services.chat.session_continuity_service import hold_session_for_continuity

pytestmark = pytest.mark.usefixtures("db_session")

CHAT_ID = "chat-rewind-hold"
REVERT_FILES = "app.services.chat.chat_turn._ChatTurnMixin._revert_files_for_messages"


@pytest.fixture(autouse=True)
def gateway() -> Iterator[AgentGateway]:
    """A private gateway standing in for the process-wide one, so no reservation leaks between tests."""
    private_gateway = AgentGateway()
    with patch("app.services.chat.session_continuity_service.get_agent_gateway", return_value=private_gateway):
        yield private_gateway


@pytest.fixture(autouse=True)
def _rewind_collaborators() -> Iterator[None]:
    """Checkpoints, goals and snapshots are not under test; the history and the session hold are."""
    with (
        patch("app.services.chat.chat_turn._ChatTurnMixin._invalidate_checkpoint_after_mutation", new_callable=AsyncMock),
        patch("app.services.chat.chat_turn._ChatTurnMixin._snapshot_pre_rewind", new_callable=AsyncMock, return_value=None),
        patch("app.services.chat.chat_turn._ChatTurnMixin._cleanup_orphan_snapshots", new_callable=AsyncMock),
        patch(
            "app.services.chat.session_continuity_service.pause_active_goal_for_rewind",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        yield


async def _persist_turn(user_message_id: str, query: str, answer: str) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=CHAT_ID,
        content=query,
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id=user_message_id,
    )
    await ChatService.persist_assistant_message_safe(chat_id=CHAT_ID, content=answer)


async def _seed_two_turns() -> None:
    await _persist_turn("msg-u1", "query 1", "answer one")
    await _persist_turn("msg-u2", "query 2", "answer two")


async def _history() -> list[str]:
    return [message.content for message in await ChatService.get_all_messages(CHAT_ID)]


@pytest.mark.asyncio
async def test_a_turn_cannot_start_while_the_files_are_reverted(gateway: AgentGateway) -> None:
    await _seed_two_turns()
    refused: list[bool] = []

    async def revert_while_a_turn_tries_to_start(chat_id: str, message_ids: list[str]) -> dict[str, list[str]]:
        try:
            gateway.reserve_session(chat_id)
        except AgentBusyError:
            refused.append(True)
        else:
            # A turn that got in persists its messages like a real one; the rewind's deletion would sweep them away.
            await _persist_turn("msg-u3", "query 3", "answer three")
            gateway.release_session(chat_id)
        return {}

    with patch(REVERT_FILES, new=revert_while_a_turn_tries_to_start):
        result = await ChatService.rewind_to_message(CHAT_ID, "msg-u2", revert_files=True)

    assert refused == [True]
    assert result.success is True
    assert result.deleted_count == 2
    assert await _history() == ["query 1", "answer one"]
    assert not gateway.is_session_active(CHAT_ID)


@pytest.mark.asyncio
async def test_the_session_is_released_when_the_file_revert_fails(gateway: AgentGateway) -> None:
    await _seed_two_turns()

    with patch(REVERT_FILES, new_callable=AsyncMock, side_effect=OSError("disk full")), pytest.raises(OSError):
        await ChatService.rewind_to_message(CHAT_ID, "msg-u2", revert_files=True)

    assert not gateway.is_session_active(CHAT_ID)
    assert await _history() == ["query 1", "answer one", "query 2", "answer two"]


@pytest.mark.asyncio
async def test_a_running_turn_refuses_the_rewind_and_keeps_its_session(gateway: AgentGateway) -> None:
    await _seed_two_turns()
    gateway.reserve_session(CHAT_ID)

    result = await ChatService.rewind_to_message(CHAT_ID, "msg-u2")

    assert (result.success, result.error) == (False, "SESSION_BUSY")
    assert gateway.is_session_active(CHAT_ID)
    assert len(await _history()) == 4


@pytest.mark.asyncio
async def test_a_draining_gateway_refuses_the_rewind(gateway: AgentGateway) -> None:
    await _seed_two_turns()
    await gateway.begin_drain()

    result = await ChatService.rewind_to_message(CHAT_ID, "msg-u2")

    assert (result.success, result.error) == (False, "SESSION_BUSY")
    assert len(await _history()) == 4


@pytest.mark.asyncio
async def test_a_second_rewind_is_refused_while_the_first_one_runs(gateway: AgentGateway) -> None:
    await _seed_two_turns()
    reverting = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_revert(chat_id: str, message_ids: list[str]) -> dict[str, list[str]]:
        reverting.set()
        await proceed.wait()
        return {}

    with patch(REVERT_FILES, new=slow_revert):
        first = asyncio.create_task(ChatService.rewind_to_message(CHAT_ID, "msg-u2", revert_files=True))
        await reverting.wait()
        second = await ChatService.rewind_to_message(CHAT_ID, "msg-u1")
        proceed.set()
        first_result = await first

    assert second.error == "SESSION_BUSY"
    assert first_result.success is True
    assert first_result.deleted_count == 2
    assert not gateway.is_session_active(CHAT_ID)


@pytest.mark.asyncio
async def test_a_session_a_stream_took_over_stays_with_the_stream(gateway: AgentGateway) -> None:
    async with hold_session_for_continuity(CHAT_ID):
        # execute_stream's hand-over: from here the stream's own finally owns the reservation.
        gateway._session_info[CHAT_ID].reserved_only = False

    assert gateway.is_session_active(CHAT_ID)
