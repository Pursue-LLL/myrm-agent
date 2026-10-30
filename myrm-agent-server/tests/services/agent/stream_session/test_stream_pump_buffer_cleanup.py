"""The pump's turn buffer: delayed cleanup removes its own run's buffer (not that of a later run under the same message id), and turn content goes to that buffer only, never onto the workspace stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

from app.services.agent.stream_session.stream_pump import pump_to_buffer
from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer

_PUMP_STREAM_PATH = "app.services.agent.stream_session.stream_pump.generate_cancellable_stream"
_CLEANUP_DELAY_SECONDS = 300


async def _stream_of(*chunks: str) -> AsyncGenerator[str]:
    for chunk in chunks:
        yield chunk


@pytest.fixture
def workspace_stream() -> Iterator[asyncio.Queue[str]]:
    """A connected workspace-stream subscriber on a fresh bus."""
    WorkspaceMultiplexer._instance = None
    watcher: asyncio.Queue[str] = asyncio.Queue()
    WorkspaceMultiplexer.get()._subscribers.add(watcher)
    yield watcher
    WorkspaceMultiplexer._instance = None


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


async def _run_pump(registry: GlobalStreamRegistry, message_id: str, *chunks: str) -> asyncio.Task[None]:
    """Pump one turn that streams ``chunks`` into a fresh buffer of ``registry``; returns its pending cleanup task."""
    session = MagicMock()
    session.pre_reply_compact_sse_sent = True
    session.request.message_id = message_id
    session.request.chat_id = "chat-cleanup"
    session.params.project_id = None
    session.is_long_running_task = False
    session.had_fatal_error = False
    session.registry = registry
    buffer = await registry.start_run(message_id)

    with patch(_PUMP_STREAM_PATH, return_value=_stream_of(*chunks)):
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


@pytest.mark.asyncio
async def test_turn_content_reaches_the_run_buffer_and_stays_off_the_workspace_stream(
    cleanup_gate: asyncio.Event, workspace_stream: asyncio.Queue[str]
) -> None:
    registry = GlobalStreamRegistry()
    chunks = ('data: {"type":"message","data":"hello"}\n\n', 'data: {"type":"message","data":"world"}\n\n')
    cleanup = await _run_pump(registry, "msg-content", *chunks)

    buffer = await registry.get_or_create("msg-content")
    # The buffer stamps each event with a resume id line; what follows it is the pumped chunk, verbatim.
    delivered = [event.partition("\n")[2] async for event in buffer.subscribe()]
    assert delivered == list(chunks)
    assert workspace_stream.empty()

    cleanup_gate.set()
    await cleanup
