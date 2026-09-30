"""Unit tests for SessionLoopManager lifecycle orchestration and stop gates."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.runtime.loop import (
    LOOP_COMPLETE_MARKER,
    LoopStatus,
    LoopStopReason,
)

from app.services.loop.session_loop_manager import SessionLoopManager


@pytest.mark.asyncio
async def test_session_loop_manager_start_and_stop() -> None:
    manager = SessionLoopManager()
    # Mock DB persistence to avoid requiring active SQLite database in pure unit test
    manager._persist_state = AsyncMock()  # type: ignore[method-assign]
    manager._hydrate_state = AsyncMock(return_value=None)  # type: ignore[method-assign]

    chat_id = "test-session-456"

    # Start loop with fixed interval
    res = await manager.start_loop(chat_id, "2m check build status --times 5")
    assert res.success
    assert res.status is not None
    assert res.status.is_active
    assert res.status.times_limit == 5
    assert res.status.mode == "interval"
    assert res.status.prompt == "check build status"

    # Verify status query
    status = await manager.get_status(chat_id)
    assert status is not None
    assert status.is_active

    # Stop loop
    stopped = await manager.stop_loop(chat_id, reason=LoopStopReason.USER_STOPPED)
    assert stopped

    # Status after stop
    status_after = await manager.get_status(chat_id)
    assert status_after is not None
    assert not status_after.is_active
    assert status_after.status == LoopStatus.STOPPED.value
    assert status_after.last_stop_reason == LoopStopReason.USER_STOPPED.value


@pytest.mark.asyncio
async def test_session_loop_manager_model_complete_signal() -> None:
    manager = SessionLoopManager()
    manager._persist_state = AsyncMock()  # type: ignore[method-assign]
    manager._hydrate_state = AsyncMock(return_value=None)  # type: ignore[method-assign]

    chat_id = "test-session-complete"

    # Hook turn executor to emit LOOP_COMPLETE on the first wakeup
    async def mock_executor(c_id: str, prompt: str) -> str:
        return f"Deploy verified and healthy.\n{LOOP_COMPLETE_MARKER}"

    manager.turn_executor = mock_executor

    res = await manager.start_loop(chat_id, "30s inspect cluster")
    assert res.success

    # Give worker brief moment to execute first tick
    await asyncio.sleep(0.15)

    status = await manager.get_status(chat_id)
    assert status is not None
    assert not status.is_active
    assert status.status == LoopStatus.COMPLETED.value
    assert status.last_stop_reason == LoopStopReason.MODEL_SIGNAL.value


@pytest.mark.asyncio
async def test_session_loop_manager_times_exhausted() -> None:
    manager = SessionLoopManager()
    manager._persist_state = AsyncMock()  # type: ignore[method-assign]
    manager._hydrate_state = AsyncMock(return_value=None)  # type: ignore[method-assign]

    chat_id = "test-session-times"

    async def mock_executor(c_id: str, prompt: str) -> str:
        return "Still waiting for build to finish..."

    manager.turn_executor = mock_executor

    # Loop with --times 1
    res = await manager.start_loop(chat_id, "30s inspect cluster --times 1")
    assert res.success

    await asyncio.sleep(0.15)

    status = await manager.get_status(chat_id)
    assert status is not None
    assert not status.is_active
    assert status.status == LoopStatus.COMPLETED.value
    assert status.last_stop_reason == LoopStopReason.TIMES_EXHAUSTED.value
