"""A command that is stopped as the shell is handed to it leaves the shell to the commands after it.

The commands of one session run one at a time under a lock, and a request can be stopped at any moment of the hand-over
from the command that finishes to the one that waits. Whatever the moment, the stop has to end with the lock free. The
session runs no shell, so each test picks its moment by counting event-loop iterations.
"""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.code_execution.session.command_stream import CANCELLED_BEFORE_START
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import wait_until
from tests.toolkits.code_execution._session_helpers import GatedSession, let_the_loop_run

_SETTLE_S = 2
# Enough iterations for a command that waits for the shell to have queued behind the running one.
_QUEUED_TICKS = 4


@pytest.mark.parametrize("ticks", range(9))
@pytest.mark.parametrize("listens_to_token", [False, True], ids=["no-token", "ambient-token"])
async def test_a_command_stopped_as_the_shell_is_handed_to_it_leaves_the_shell_free(
    ticks: int, listens_to_token: bool
) -> None:
    session = GatedSession()
    first = asyncio.create_task(session.execute("hold first"))
    await wait_until(lambda: session.ran == ["hold first"])

    # In a run the request's token is ambient: it is what a command waiting for the shell listens to.
    token = CancellationToken("req-handover") if listens_to_token else None
    set_cancel_token(token)
    try:
        second = asyncio.create_task(session.execute("second", cancel_token=token))
    finally:
        set_cancel_token(None)
    await let_the_loop_run(_QUEUED_TICKS)

    session.release("hold first")
    await let_the_loop_run(ticks)
    second.cancel()
    await asyncio.gather(first, second, return_exceptions=True)

    async with asyncio.timeout(_SETTLE_S):
        follow_up = await session.execute("third")
    assert follow_up.success, "the stopped command took the shell with it"


async def test_a_request_stopped_before_its_command_asked_for_the_shell_leaves_the_shell_free() -> None:
    session = GatedSession()
    token = CancellationToken("req-stopped")
    token.cancel(CancelReason.USER_CANCELLED)
    set_cancel_token(token)
    try:
        dropped = await session.execute("second", cancel_token=token)
    finally:
        set_cancel_token(None)
    await let_the_loop_run(_QUEUED_TICKS)

    assert dropped.error == CANCELLED_BEFORE_START
    async with asyncio.timeout(_SETTLE_S):
        follow_up = await session.execute("third")
    assert follow_up.success, "the dropped command took the shell with it"
