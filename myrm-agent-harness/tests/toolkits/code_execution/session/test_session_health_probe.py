"""A shell that is in use is not probed, so a health check never queues behind a command.

``get_or_create_bash_session`` probes the shell it finds while it holds the run's start lock, so a probe that waited
for the command the shell is running would hold up every caller that comes after it, and none of them can leave
while it waits. The session runs no shell: each test picks the moment of the probe by counting event-loop iterations.
"""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import wait_until
from tests.toolkits.code_execution._session_helpers import GatedSession, let_the_loop_run

_SETTLE_S = 2
# Enough iterations for a command that waits for the shell to have queued behind the running one.
_QUEUED_TICKS = 4


async def test_an_idle_shell_is_probed() -> None:
    session = GatedSession()

    assert await session.check_health()
    assert session.ran == ["echo ok"]


async def test_a_probe_does_not_wait_for_the_command_the_shell_is_running() -> None:
    session = GatedSession()
    running = asyncio.create_task(session.execute("hold first"))
    await wait_until(lambda: session.ran == ["hold first"])

    async with asyncio.timeout(_SETTLE_S):
        healthy = await session.check_health()

    assert healthy
    assert session.ran == ["hold first"], "the probe has to leave the shell to the command that runs in it"
    session.release("hold first")
    assert (await running).success


async def test_a_probe_does_not_wait_for_a_command_that_asked_for_the_shell_before_it() -> None:
    session = GatedSession()
    # Both tasks start in the same loop iteration: the command waits for the shell but has not taken it yet.
    running = asyncio.create_task(session.execute("hold first"))
    probe = asyncio.create_task(session.check_health())

    async with asyncio.timeout(_SETTLE_S):
        healthy = await probe

    assert healthy
    assert session.ran == [], "the probe has to leave the shell to the command that asked first"
    await wait_until(lambda: session.ran == ["hold first"])
    session.release("hold first")
    assert (await running).success


@pytest.mark.parametrize("ticks", range(9))
async def test_a_probe_does_not_wait_for_the_command_the_shell_is_handed_to(ticks: int) -> None:
    session = GatedSession()
    first = asyncio.create_task(session.execute("hold first"))
    await wait_until(lambda: session.ran == ["hold first"])
    second = asyncio.create_task(session.execute("hold second"))
    await let_the_loop_run(_QUEUED_TICKS)

    session.release("hold first")
    await let_the_loop_run(ticks)
    async with asyncio.timeout(_SETTLE_S):
        healthy = await session.check_health()

    assert healthy
    await wait_until(lambda: session.ran == ["hold first", "hold second"])
    session.release("hold second")
    assert all(result.success for result in await asyncio.gather(first, second))
    assert session.ran == ["hold first", "hold second"], "the probe never reached the shell"


async def test_a_probe_whose_request_was_already_stopped_does_not_call_the_shell_dead() -> None:
    session = GatedSession()
    token = CancellationToken("req-stopped")
    token.cancel(CancelReason.USER_CANCELLED)
    set_cancel_token(token)
    try:
        healthy = await session.check_health()
    finally:
        set_cancel_token(None)

    assert healthy, "a probe that never ran learned nothing, so the caller must not restart the shell"
    assert session.ran == []
