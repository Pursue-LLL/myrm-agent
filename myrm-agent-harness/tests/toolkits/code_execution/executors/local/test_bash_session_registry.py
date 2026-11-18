"""One shell per run identity, however many commands of the run arrive together.

The parallel sub-agents of a run share its shell. These tests drive the registry the local executor keeps, with real
shells: commands that arrive together start one shell, and a caller that checks a shell another command is running
waits for that command instead of restarting its shell.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession
from myrm_agent_harness.toolkits.code_execution.session.models import SessionExecutionResult
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import wait_until
from tests.toolkits.code_execution._session_helpers import hold_command

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")

_SETTLE_S = 10
# How long a call that must still be waiting is watched before the test goes on.
_STILL_WAITING_S = 0.5


@pytest.fixture
async def executor(tmp_path: Path) -> AsyncIterator[LocalExecutor]:
    local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
    try:
        yield local
    finally:
        await local.close()


def _context(session_id: str) -> ExecutionContext:
    return ExecutionContext(code="true", session_id=session_id)


@dataclass(frozen=True)
class _BusyShell:
    context: ExecutionContext
    session: LocalPersistentSession
    gate: Path
    running: asyncio.Task[SessionExecutionResult]


async def _busy_shell(executor: LocalExecutor, tmp_path: Path) -> _BusyShell:
    """A shell that is running a command which holds it until the test creates ``gate``."""
    context = _context("busy")
    session = await executor._get_or_create_bash_session(context, executor._build_bash_env(None))
    started, gate = tmp_path / "started", tmp_path / "gate"
    running = asyncio.create_task(session.execute(hold_command(started, gate)))
    await wait_until(started.exists)
    return _BusyShell(context, session, gate, running)


async def test_commands_that_arrive_together_start_one_shell(
    executor: LocalExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[int] = []
    create_process = LocalPersistentSession._create_process

    async def counting(self: LocalPersistentSession) -> asyncio.subprocess.Process:
        process = await create_process(self)
        spawned.append(process.pid)
        return process

    monkeypatch.setattr(LocalPersistentSession, "_create_process", counting)

    env = executor._build_bash_env(None)
    sessions = await asyncio.gather(*(executor._get_or_create_bash_session(_context("shared"), env) for _ in range(4)))

    assert len({id(session) for session in sessions}) == 1
    assert len(spawned) == 1
    assert len(executor._bash_sessions) == 1


async def test_a_caller_that_checks_a_busy_shell_waits_for_its_command(executor: LocalExecutor, tmp_path: Path) -> None:
    busy = await _busy_shell(executor, tmp_path)
    assert busy.session.process is not None
    pid = busy.session.process.pid

    checking = asyncio.create_task(executor._get_or_create_bash_session(busy.context, executor._build_bash_env(None)))
    finished, _ = await asyncio.wait({checking}, timeout=_STILL_WAITING_S)
    assert not finished, "the check runs a command, so it has to wait for the one the shell is running"

    # The wait is for that shell only: another run is not held up by it.
    other = await asyncio.wait_for(
        executor._get_or_create_bash_session(_context("other"), executor._build_bash_env(None)), _SETTLE_S
    )
    assert other is not busy.session

    busy.gate.touch()
    async with asyncio.timeout(_SETTLE_S):
        result, checked = await asyncio.gather(busy.running, checking)

    assert result.success and result.stdout == "released", "the command that was running was not interrupted"
    assert checked is busy.session
    assert busy.session.process is not None and busy.session.process.pid == pid, "the shell was not restarted"


async def test_a_caller_stopped_while_it_checks_a_busy_shell_leaves_the_shell_alone(
    executor: LocalExecutor, tmp_path: Path
) -> None:
    busy = await _busy_shell(executor, tmp_path)

    # In a run the request's token is ambient, which is what a command waiting for the shell listens to.
    token = CancellationToken("req-check")
    set_cancel_token(token)
    try:
        checking = asyncio.create_task(
            executor._get_or_create_bash_session(busy.context, executor._build_bash_env(None))
        )
    finally:
        set_cancel_token(None)
    finished, _ = await asyncio.wait({checking}, timeout=_STILL_WAITING_S)
    assert not finished, "the shell is busy, so the check has to be waiting"

    token.cancel(CancelReason.USER_CANCELLED)
    async with asyncio.timeout(_SETTLE_S):
        checked = await checking

    assert checked is busy.session, "a check that never ran learned nothing, so the shell is not called dead"
    busy.gate.touch()
    result = await busy.running
    assert result.success and result.stdout == "released"
