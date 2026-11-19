"""A shell that is ended under its command fails that command and is rebuilt for the next one.

Two ways end a shell while a command runs. A signal sent to it ends it through the marker path, and bash then reports
the status of the last command that finished instead of the signal's; the shell has to report the signal. And
``close()`` clears the session's process while the command still reads from it; the command has to end as a failure
instead of raising. These tests drive real shells.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.models import SessionState
from tests.support.marked_processes import wait_until
from tests.toolkits.code_execution._session_helpers import state_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")

_SETTLE_S = 15


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[LocalPersistentSession]:
    config = SessionConfig(session_id="ended-under-command", work_dir=str(tmp_path), timeout=30, sandbox_mode="disable")
    shell = LocalPersistentSession(config)
    await shell.start()
    try:
        yield shell
    finally:
        await shell.close()


@pytest.mark.parametrize(
    ("signal_name", "exit_code"),
    [("TERM", 143), ("HUP", 129), ("INT", 130)],
)
async def test_a_shell_ended_by_a_signal_fails_its_command_with_that_signal(
    session: LocalPersistentSession, signal_name: str, exit_code: int
) -> None:
    assert (await session.execute("export KEEP=1")).success

    ended = await session.execute(f"echo before; kill -{signal_name} $$; echo after")

    assert not ended.success
    assert ended.exit_code == exit_code
    assert ended.error is None, "the shell ended through its markers, which is not a crash"
    assert ended.stdout == "before", "the command went on after its shell was told to end"

    assert session.process is not None
    await asyncio.wait_for(session.process.wait(), _SETTLE_S)
    follow_up = await session.execute('echo "[${KEEP:-fresh}]"')
    assert follow_up.success
    assert follow_up.stdout == "[fresh]", "the next command runs in a new shell"


@pytest.mark.parametrize(
    "command",
    [
        "while true; do sleep 0.05; done",
        "while true; do echo line; sleep 0.01; done",
        "sleep 100",
        "grep zzz /dev/null; sleep 100",
        "trap '' TERM; sleep 100",
    ],
    ids=["silent-loop", "streaming-loop", "sleep", "grep-then-sleep", "term-ignored"],
)
async def test_a_shell_closed_under_a_command_ends_it_as_a_failure(
    session: LocalPersistentSession, tmp_path: Path, command: str
) -> None:
    started = tmp_path / "started"
    running = asyncio.create_task(session.execute(f"touch {started}; {command}"))
    await wait_until(started.exists)

    await session.close()

    async with asyncio.timeout(_SETTLE_S):
        result = await running
    assert not result.success
    assert state_of(session) == SessionState.TERMINATED
