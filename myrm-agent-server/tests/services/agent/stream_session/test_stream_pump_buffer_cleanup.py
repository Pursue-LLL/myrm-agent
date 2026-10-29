"""The pump's delayed buffer cleanup removes its own run's buffer, not the buffer of a later run under the same message id."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

from app.services.agent.stream_session.stream_pump import pump_to_buffer

_PUMP_STREAM_PATH = "app.services.agent.stream_session.stream_pump.generate_cancellable_stream"
_MUX_PATH = "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer"
_CLEANUP_DELAY_SECONDS = 300


async def _empty_stream() -> AsyncGenerator[str]:
    if False:
        yield ""


@pytest.fixture
def cleanup_gate(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """Hold the 300 s cleanup delay until the test opens the gate."""
    gate = asyncio.Event()
    real_sleep = asyncio.sleep

    async def _sleep(delay: float, *args: object) -> None:
        if delay == _CLEANUP_DELAY_SECONDS:
            await gate.wait()
            return
        await real_sleep(delay, *args)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    return gate


async def _run_pump(registry: GlobalStreamRegistry, message_id: str) -> asyncio.Task[None]:
    """Pump one empty turn into a fresh buffer of ``registry``; returns its pending cleanup task."""
    session = MagicMock()
    session.pre_reply_compact_sse_sent = True
    session.request.message_id = message_id
    session.request.chat_id = "chat-cleanup"
    session.params.project_id = None
    session.is_long_running_task = False
    session.had_fatal_error = False
    session.registry = registry
    buffer = await registry.start_run(message_id)

    with patch(_PUMP_STREAM_PATH, return_value=_empty_stream()), patch(_MUX_PATH) as mux:
        mux.get.return_value.publish = AsyncMock()
        await pump_to_buffer(session, buffer)

    (cleanup,) = [task for task in asyncio.all_tasks() if task.get_name() == f"buffer_cleanup_{message_id}"]
    return cleanup


@pytest.mark.asyncio
async def test_cleanup_removes_the_buffer_of_a_run_nobody_replaced(cleanup_gate: asyncio.Event) -> None:
    registry = GlobalStreamRegistry()
    cleanup = await _run_pump(registry, "msg-cleanup-alone")

    cleanup_gate.set()
    await cleanup

    assert not await registry.has_buffer("msg-cleanup-alone")


@pytest.mark.asyncio
async def test_cleanup_leaves_the_buffer_of_a_run_that_resumed_under_the_same_id(cleanup_gate: asyncio.Event) -> None:
    registry = GlobalStreamRegistry()
    cleanup = await _run_pump(registry, "msg-cleanup-resumed")
    resumed = await registry.start_run("msg-cleanup-resumed")

    cleanup_gate.set()
    await cleanup

    assert await registry.get_or_create("msg-cleanup-resumed") is resumed
    await resumed.append('data: {"type":"message","data":"after-approval"}\n\n')
    await resumed.end_stream()
    assert len([event async for event in resumed.subscribe()]) == 1
