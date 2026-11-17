"""A turn the user stopped before its stream ran takes its replay marker with it, and only its own.

Uses the real SQLite database: the marker is what the crash auto-continue replays after a restart, so a stopped turn
that left it behind would be answered on the next boot although the user cancelled it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models.chat import InterruptedTurnMarker
from app.services.agent.stream_session.orchestrator_turn_body import write_interrupted_turn_marker
from app.services.agent.stream_session.stream_finalize import release_unfinished_turn
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


async def _write_marker(chat_id: str, message_id: str) -> str:
    request = MagicMock()
    request.chat_id = chat_id
    request.message_id = message_id
    request.action_mode = "fast"
    request.agent_id = "test-agent"
    params = MagicMock()
    params.model_dump.return_value = {"query": "q", "model_cfg": {"provider": "test"}}
    return await write_interrupted_turn_marker(request, params, user_message_id=message_id)


async def _marker_ids(session_factory: async_sessionmaker[AsyncSession], chat_id: str) -> list[str]:
    async with session_factory() as db:
        rows = await db.execute(select(InterruptedTurnMarker.id).where(InterruptedTurnMarker.chat_id == chat_id))
        return list(rows.scalars())


def _unfinished_turn(chat_id: str, marker_id: str, *, stopped: bool) -> AgentStreamSession:
    """The part of a turn's session the safety net reads, for a turn whose stream never reached finalize."""
    token = CancellationToken(request_id=f"msg-{chat_id}")
    if stopped:
        token.cancel(CancelReason.USER_CANCELLED)
    return cast(
        "AgentStreamSession",
        SimpleNamespace(
            request=SimpleNamespace(chat_id=chat_id, message_id=f"msg-{chat_id}", agent_id="test-agent"),
            params=SimpleNamespace(message_id=f"msg-{chat_id}"),
            cancel_token=token,
            steering_token=None,
            goal_provider=None,
            collector=MagicMock(),
            digest_run=None,
            turn_marker_id=marker_id,
            torn_down=False,
            had_fatal_error=False,
        ),
    )


@pytest.mark.asyncio
async def test_writing_a_marker_returns_the_id_of_its_row(session_factory, test_chat):
    marker_id = await _write_marker(test_chat, "msg-1")

    assert await _marker_ids(session_factory, test_chat) == [marker_id]


@pytest.mark.asyncio
async def test_a_turn_stopped_before_its_stream_ran_takes_its_marker_with_it(session_factory, test_chat):
    marker_id = await _write_marker(test_chat, "msg-1")

    await release_unfinished_turn(_unfinished_turn(test_chat, marker_id, stopped=True))

    assert await _marker_ids(session_factory, test_chat) == []


@pytest.mark.asyncio
async def test_a_turn_that_failed_before_its_stream_ran_keeps_its_marker_for_the_crash_replay(session_factory, test_chat):
    marker_id = await _write_marker(test_chat, "msg-1")

    await release_unfinished_turn(_unfinished_turn(test_chat, marker_id, stopped=False))

    assert await _marker_ids(session_factory, test_chat) == [marker_id]


@pytest.mark.asyncio
async def test_a_stopped_turn_that_ends_late_leaves_the_marker_of_the_turn_that_followed(session_factory, test_chat):
    stopped_turn = _unfinished_turn(test_chat, await _write_marker(test_chat, "msg-1"), stopped=True)
    next_marker_id = await _write_marker(test_chat, "msg-2")

    await release_unfinished_turn(stopped_turn)

    assert await _marker_ids(session_factory, test_chat) == [next_marker_id]
