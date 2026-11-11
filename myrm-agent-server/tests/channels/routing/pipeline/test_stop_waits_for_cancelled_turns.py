"""A stopping router waits, for a bounded time, for the turns it cancelled to finish unwinding.

A cancelled turn still needs the event loop to release what it holds (its database session, its channel resources).
``stop`` is followed by the shutdown of what the turns share, so it lets the cancelled turns finish first; a turn that
has not finished within ``_SHUTDOWN_TURN_GRACE_SECONDS`` is left behind with a warning instead of holding the shutdown up.
"""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.routing.pipeline import lifecycle
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _ActiveTask

from ..risk_gate_testkit import make_router


class _Turn:
    """A running turn that, once cancelled, needs the event loop for ``unwind_seconds`` before it is gone."""

    def __init__(self, router: AgentRouter, chat_id: str, unwind_seconds: float) -> None:
        self.unwound = asyncio.Event()
        self._unwind_seconds = unwind_seconds
        self.task = asyncio.create_task(self._run())
        router._active_tasks[f"telegram:{chat_id}"] = _ActiveTask(
            task=self.task,
            cancel_token=MagicMock(spec=CancellationToken),
            channel="telegram",
            chat_id=chat_id,
            placeholder_id=None,
            started_at=time.monotonic(),
        )

    async def _run(self) -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await asyncio.sleep(self._unwind_seconds)
            self.unwound.set()
            raise


async def _start_turns(router: AgentRouter, *unwind_seconds: float) -> list[_Turn]:
    turns = [_Turn(router, f"chat-{index}", seconds) for index, seconds in enumerate(unwind_seconds)]
    # A task cancelled before its first step never reaches its handler, so the turns run up to their first await first.
    await asyncio.sleep(0)
    return turns


@pytest.mark.asyncio
async def test_stop_returns_only_after_the_cancelled_turns_have_unwound(caplog: pytest.LogCaptureFixture) -> None:
    router = make_router()
    turns = await _start_turns(router, 0.2, 0.05)

    with caplog.at_level(logging.WARNING, logger=lifecycle.logger.name):
        await router.stop()

    assert all(turn.unwound.is_set() for turn in turns)
    assert all(turn.task.cancelled() for turn in turns)
    assert "still unwinding" not in caplog.text


@pytest.mark.asyncio
async def test_stop_gives_up_on_a_turn_that_does_not_unwind_in_time(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(lifecycle, "_SHUTDOWN_TURN_GRACE_SECONDS", 0.2)
    router = make_router()
    stuck, quick = await _start_turns(router, 30.0, 0.0)

    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger=lifecycle.logger.name):
        await router.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 3.0
    assert quick.unwound.is_set()
    assert not stuck.unwound.is_set()
    assert "1 cancelled turn(s) still unwinding after 0.2s" in caplog.text

    stuck.task.cancel()
    await asyncio.gather(stuck.task, return_exceptions=True)
