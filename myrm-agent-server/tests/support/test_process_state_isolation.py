"""The registries that tests would otherwise leave in a state the next test reads."""

from __future__ import annotations

import asyncio

import pytest
from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks
from myrm_agent_harness.api import track_background_task

from tests.support.process_state_isolation import forget_tasks_of_closed_loops


def _task_left_pending_on_a_closed_loop() -> asyncio.Task[None]:
    """What a streamed agent turn leaves behind when the loop of its TestClient closes before its cleanup finished.

    Runs on a worker thread: a loop cannot be driven from inside a running one.
    """
    loop = asyncio.new_event_loop()
    task = loop.create_task(asyncio.sleep(3600))
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    task._log_destroy_pending = False  # no loop will ever resume it, so its destruction is not an event
    return task


@pytest.mark.asyncio
async def test_a_drain_waits_for_a_live_task_after_the_tasks_of_closed_loops_were_forgotten() -> None:
    """With the stale task still registered, the drain's ``gather`` raises and returns before the live task is done."""
    stale = await asyncio.to_thread(_task_left_pending_on_a_closed_loop)
    track_background_task(stale)

    async def finish_soon() -> None:
        await asyncio.sleep(0.05)

    live = asyncio.create_task(finish_soon())
    track_background_task(live)

    forget_tasks_of_closed_loops()
    await wait_all_background_tasks(timeout_seconds=5)

    assert live.done()
