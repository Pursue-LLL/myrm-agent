"""The commands of one persistent shell run one at a time, and a command that killed its shell is not run again.

A shell has one stdin and one stdout, and the parallel sub-agents of a run share it. These tests drive real shells: a
second command waits for the first instead of reading its output, a request that is stopped while its command waits
drops it, and a shell that died under a command ran it once, said so, and left the next command a fresh shell.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.command_stream import CANCELLED_BEFORE_START
from myrm_agent_harness.toolkits.code_execution.session.models import SessionState
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import wait_until
from tests.toolkits.code_execution._session_helpers import hold_command, state_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")

_SETTLE_S = 10
# How long a command that must still be waiting is watched before the test goes on.
_STILL_WAITING_S = 0.5


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[LocalPersistentSession]:
    config = SessionConfig(session_id="exclusion", work_dir=str(tmp_path), timeout=30, sandbox_mode="disable")
    shell = LocalPersistentSession(config)
    await shell.start()
    try:
        yield shell
    finally:
        await shell.close()


async def test_commands_of_one_session_run_one_at_a_time(session: LocalPersistentSession, tmp_path: Path) -> None:
    started, gate, order = tmp_path / "started", tmp_path / "gate", tmp_path / "order.txt"
    first = asyncio.create_task(
        session.execute(f"echo first-start >> {order}; {hold_command(started, gate)}; echo first-end >> {order}")
    )
    await wait_until(started.exists)
    second = asyncio.create_task(session.execute(f"echo second >> {order}; echo second-out"))

    finished, _ = await asyncio.wait({second}, timeout=_STILL_WAITING_S)
    assert not finished, "the shell is running the first command, so the second has to wait for it"

    gate.touch()
    async with asyncio.timeout(_SETTLE_S):
        first_result, second_result = await asyncio.gather(first, second)

    assert first_result.success and first_result.stdout == "released"
    assert second_result.success and second_result.stdout == "second-out"
    assert order.read_text().splitlines() == ["first-start", "first-end", "second"]


async def test_a_command_waiting_for_the_shell_is_dropped_when_its_request_is_stopped(
    session: LocalPersistentSession, tmp_path: Path
) -> None:
    started, gate, ran = tmp_path / "started", tmp_path / "gate", tmp_path / "ran"
    first = asyncio.create_task(session.execute(hold_command(started, gate)))
    await wait_until(started.exists)

    # In a run the request's token is ambient, which is what a command waiting for the shell listens to.
    token = CancellationToken("req-queued")
    set_cancel_token(token)
    try:
        queued = asyncio.create_task(session.execute(f"touch {ran}", cancel_token=token))
    finally:
        set_cancel_token(None)
    finished, _ = await asyncio.wait({queued}, timeout=_STILL_WAITING_S)
    assert not finished, "the shell is busy, so the command has to be waiting"

    token.cancel(CancelReason.USER_CANCELLED)
    async with asyncio.timeout(_SETTLE_S):
        dropped = await queued

    assert dropped.error == CANCELLED_BEFORE_START
    assert not ran.exists()
    gate.touch()
    assert (await first).stdout == "released", "the command that was running never noticed"
    assert (await session.execute("echo after")).stdout == "after", "the queue still works"


async def test_a_command_that_kills_its_shell_ran_once_and_leaves_a_fresh_shell(
    session: LocalPersistentSession, tmp_path: Path
) -> None:
    counter = tmp_path / "runs.txt"
    assert (await session.execute("export KEEP=1")).success

    died = await session.execute(f"echo run >> {counter}; kill -9 $$")

    assert not died.success
    assert died.error is not None
    assert "Session process ended unexpectedly" in died.error
    assert "may have been only partially applied" in died.error
    assert counter.read_text().splitlines() == ["run"], "a command that may have run is not given to a new shell"
    assert state_of(session) == SessionState.TERMINATED
    follow_up = await session.execute('echo "[${KEEP:-fresh}]"')
    assert follow_up.success
    assert follow_up.stdout == "[fresh]"
