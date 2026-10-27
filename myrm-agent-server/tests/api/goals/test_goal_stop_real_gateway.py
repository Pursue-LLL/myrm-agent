"""A turn told to stop holds a resume back, whoever started it, checked against the real gateway.

A goal turn the server starts on its own (a follow-up after a finished turn, a resume, a wake after a background
job) has no cancel token and no message id; only the chat turn of a sent message has both. Both are stopped by a
pause, and a resume right after must wait for either, not only for the one with a token.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals import goal_controls
from app.services.agent.goals.goal_registry import GoalRegistry


class _Turn:
    """A running turn that is silent until the test lets its next event through, like an agent waiting on a tool."""

    def __init__(self, session_id: str, message_id: str | None) -> None:
        self._gate = asyncio.Event()
        self.task = asyncio.create_task(self._run(session_id, message_id))

    async def _events(self) -> AsyncIterator[dict[str, object]]:
        for i in range(50):
            await self._gate.wait()
            self._gate.clear()
            yield {"type": "tick", "i": i}

    async def _run(self, session_id: str, message_id: str | None) -> None:
        async for _ in get_agent_gateway().execute_stream(
            self._events(), agent_type="general", session_id=session_id, active_message_id=message_id
        ):
            pass

    def release_event(self) -> None:
        self._gate.set()


class _Turns:
    """Starts turns on the real gateway and ends whatever a test left running."""

    def __init__(self) -> None:
        self._turns: list[_Turn] = []
        self._message_ids: list[str] = []

    async def start(self, session_id: str, *, chat_turn: bool) -> _Turn:
        """A chat turn has a message id and a registered token; a server-started one has neither."""
        message_id: str | None = None
        if chat_turn:
            message_id = f"msg-{uuid.uuid4().hex[:8]}"
            CancellationRegistry.register(CancellationToken(request_id=message_id))
            self._message_ids.append(message_id)
        turn = _Turn(session_id, message_id)
        self._turns.append(turn)
        while not get_agent_gateway().is_session_active(session_id):
            await asyncio.sleep(0.005)
        return turn

    async def close(self) -> None:
        for turn in self._turns:
            turn.task.cancel()
        await asyncio.gather(*(turn.task for turn in self._turns), return_exceptions=True)
        for message_id in self._message_ids:
            CancellationRegistry.unregister(message_id)


@pytest.fixture
async def turns() -> AsyncIterator[_Turns]:
    runner = _Turns()
    yield runner
    await runner.close()


@pytest.fixture
def session_id() -> Iterator[str]:
    sid = f"goal-real-gateway-{uuid.uuid4().hex[:8]}"
    yield sid
    GoalRegistry.unregister(sid)


@pytest.fixture
async def api(tmp_path: Path, goal_stream_trigger: AsyncMock) -> AsyncIterator[httpx.AsyncClient]:
    """The goals router served in the test's own event loop, so a turn and a request share one gateway loop."""
    from app.api.goals.router import router as goals_router

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")
    with (
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))),
        patch("app.api.goals.router.get_features") as features,
    ):
        features.return_value.get_bool.return_value = True
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def _active_goal(session_id: str) -> Goal:
    return await GoalRegistry.get_or_create_provider(session_id).create_goal(session_id, "Ship the report")


@pytest.mark.parametrize("chat_turn", [False, True], ids=["started_by_server", "chat_turn"])
async def test_a_turn_told_to_stop_is_stopping_until_it_winds_down(turns: _Turns, session_id: str, chat_turn: bool) -> None:
    goal = await _active_goal(session_id)
    turn = await turns.start(session_id, chat_turn=chat_turn)
    assert not goal_controls.is_turn_stopping(session_id)

    assert goal_controls.stop_goal_turn(session_id, goal)

    assert goal_controls.is_turn_stopping(session_id)
    turn.release_event()
    await turn.task
    assert not goal_controls.is_turn_stopping(session_id)


@pytest.mark.parametrize("chat_turn", [False, True], ids=["started_by_server", "chat_turn"])
async def test_a_turn_that_was_not_told_to_stop_does_not_hold_a_resume_back(
    turns: _Turns, session_id: str, chat_turn: bool
) -> None:
    await turns.start(session_id, chat_turn=chat_turn)

    assert not goal_controls.is_turn_stopping(session_id)
    assert await asyncio.wait_for(goal_controls.wait_for_stopped_turn(session_id), timeout=0.5)


async def test_the_turn_after_a_stopped_one_is_not_stopping(turns: _Turns, session_id: str) -> None:
    goal = await _active_goal(session_id)
    first = await turns.start(session_id, chat_turn=False)
    goal_controls.stop_goal_turn(session_id, goal)
    first.release_event()
    await first.task

    await turns.start(session_id, chat_turn=False)

    assert not goal_controls.is_turn_stopping(session_id)


@pytest.mark.parametrize("chat_turn", [False, True], ids=["started_by_server", "chat_turn"])
async def test_resume_right_after_pause_waits_for_the_turn_then_starts_one_turn(
    api: httpx.AsyncClient, goal_stream_trigger: AsyncMock, turns: _Turns, session_id: str, chat_turn: bool
) -> None:
    await _active_goal(session_id)
    turn = await turns.start(session_id, chat_turn=chat_turn)
    session_busy_when_started: list[bool] = []

    async def record_busy(*_args: object, **_kwargs: object) -> bool:
        session_busy_when_started.append(get_agent_gateway().is_session_active(session_id))
        return True

    goal_stream_trigger.side_effect = record_busy

    pause = await api.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})
    asyncio.get_running_loop().call_later(0.2, turn.release_event)
    resume = await api.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})
    await turn.task

    assert pause.status_code == 200
    assert resume.status_code == 200
    assert resume.json()["new_status"] == "active"
    goal_stream_trigger.assert_awaited_once()
    assert session_busy_when_started == [False]


async def test_resume_is_refused_while_a_server_started_turn_is_still_stopping(
    api: httpx.AsyncClient, goal_stream_trigger: AsyncMock, turns: _Turns, session_id: str
) -> None:
    goal = await _active_goal(session_id)
    turn = await turns.start(session_id, chat_turn=False)

    pause = await api.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})
    with patch.object(goal_controls, "_STOP_WAIT_SECONDS", 0.1):
        resume = await api.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})
    turn.release_event()
    await turn.task

    assert pause.status_code == 200
    assert resume.status_code == 409
    stored = await GoalRegistry.get_or_create_provider(session_id).get_goal(goal.goal_id)
    assert stored is not None
    assert stored.status is GoalStatus.PAUSED
    goal_stream_trigger.assert_not_awaited()
