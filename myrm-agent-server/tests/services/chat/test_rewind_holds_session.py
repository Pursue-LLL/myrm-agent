"""A rewind holds the chat from its first step to its last.

Between the file revert and the message deletion, a turn that started would be mixed up with the rewind. Holding the
chat's gateway session makes every entry that reserves it first refuse instead, and an IM turn, which the gateway cannot
see, is refused through the busy probe.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.adaptive_wakeup.chat_busy import set_chat_busy_probe
from app.services.agent.gateway import AgentBusyError, AgentGateway
from app.services.chat.chat_service import ChatService
from app.services.chat.session_continuity_service import hold_session_for_continuity

pytestmark = pytest.mark.usefixtures("db_session", "rewind_collaborators")

CHAT_ID = "chat-rewind-hold"
REVERT_FILES = "app.services.chat.chat_turn.revert_files_for_messages"


class ImTurnRunning:
    """The IM router has a turn running in ``CHAT_ID``."""

    def is_busy(self, chat_id: str) -> bool:
        return chat_id == CHAT_ID


@pytest.fixture(autouse=True)
def gateway() -> Iterator[AgentGateway]:
    """A private gateway standing in for the process-wide one, so no reservation leaks between tests."""
    private_gateway = AgentGateway()
    with patch("app.services.agent.turn_lease.lease.get_agent_gateway", return_value=private_gateway):
        yield private_gateway


@pytest.fixture(autouse=True)
def _no_im_turn() -> Iterator[None]:
    """The busy probe is process-wide state: start every test without one and leave none behind."""
    set_chat_busy_probe(None)
    yield
    set_chat_busy_probe(None)


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
async def test_an_im_turn_the_gateway_cannot_see_refuses_the_rewind_before_anything_is_touched(gateway: AgentGateway) -> None:
    await _seed_two_turns()
    set_chat_busy_probe(ImTurnRunning())

    with patch(REVERT_FILES, new_callable=AsyncMock) as revert:
        result = await ChatService.rewind_to_message(CHAT_ID, "msg-u2", revert_files=True)

    assert (result.success, result.error) == (False, "SESSION_BUSY")
    revert.assert_not_awaited()
    assert not gateway.is_session_active(CHAT_ID)
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
async def test_a_gateway_error_raised_inside_the_hold_is_not_taken_for_a_busy_chat(gateway: AgentGateway) -> None:
    with pytest.raises(AgentBusyError):
        async with hold_session_for_continuity(CHAT_ID):
            raise AgentBusyError("raised by the caller's own step")

    assert not gateway.is_session_active(CHAT_ID)


@pytest.mark.asyncio
async def test_a_session_a_stream_took_over_stays_with_the_stream(gateway: AgentGateway) -> None:
    async with hold_session_for_continuity(CHAT_ID):
        # execute_stream's hand-over: from here the stream's own finally owns the reservation.
        gateway._session_info[CHAT_ID].reserved_only = False

    assert gateway.is_session_active(CHAT_ID)
