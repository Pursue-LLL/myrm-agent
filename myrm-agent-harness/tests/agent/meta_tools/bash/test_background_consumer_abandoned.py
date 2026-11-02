"""A background consumer closed unfinished must not wait on the registry lock; a cancelled one still finishes."""

from __future__ import annotations

import asyncio
import gc
import threading
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.test_background_registry import _FakeProc

# The collection finishes in milliseconds; the deadline only bounds the failure when it never does.
_COLLECTION_DEADLINE_S = 10.0


async def _register_a_job_that_never_ends(registry: BackgroundProcessRegistry, *, pid: int) -> None:
    proc = _FakeProc(pid=pid, stdout=[], stderr=[])
    await registry.register(cast(AsyncProcessProtocol, proc), command="sleep 999", session_id="s-abandoned")
    await asyncio.sleep(0)  # the consumer is now waiting for the process to exit


def test_a_consumer_collected_while_the_registry_lock_is_held_does_not_wait_for_it() -> None:
    """``register()`` holds the lock while it walks the entries, and the collector can run in the middle of that walk."""
    registry = BackgroundProcessRegistry()
    loop = asyncio.new_event_loop()
    collector_was_on = gc.isenabled()
    gc.disable()  # the abandoned consumer must be collected by the call below, not earlier
    try:
        loop.run_until_complete(_register_a_job_that_never_ends(registry, pid=9500))
        registry._entries.clear()  # the consumer task loses its last reference
        loop.close()

        def collect_while_holding_the_lock() -> None:
            with registry._lock:
                gc.collect()

        collector = threading.Thread(target=collect_while_holding_the_lock, daemon=True)
        collector.start()
        collector.join(_COLLECTION_DEADLINE_S)
        assert not collector.is_alive(), "collecting an abandoned consumer waits for a lock its own thread holds"
    finally:
        if collector_was_on:
            gc.enable()


@pytest.mark.asyncio
async def test_a_cancelled_consumer_still_finishes_the_job() -> None:
    """Only a coroutine closed by the collector skips the finish; a cancelled task has a loop and delivers it."""
    finished: list[int] = []

    async def on_finish(info: BackgroundProcessInfo) -> None:
        finished.append(info.pid)

    registry = BackgroundProcessRegistry()
    proc = _FakeProc(pid=9501, stdout=[], stderr=[])
    await registry.register(
        cast(AsyncProcessProtocol, proc), command="sleep 999", session_id="s-cancelled", finish_listener=on_finish
    )
    await asyncio.sleep(0)

    reader = registry._entries[9501].reader_task
    assert reader is not None
    reader.cancel()
    await asyncio.gather(reader, return_exceptions=True)

    assert finished == [9501]
