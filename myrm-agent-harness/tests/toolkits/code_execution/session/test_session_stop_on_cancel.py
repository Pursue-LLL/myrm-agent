"""A cancelled request stops the command its shell is running.

Cancelling a request only flips a flag, and the shell command the agent started has to notice it. These tests drive
real shells and real processes: the whole process tree dies, the partial output survives, the command is never run
a second time, and the next command gets a working (fresh) shell.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_SETTLE_S = 10


def _config(work_dir: Path, *, sandbox_mode: str = "disable", timeout: int = 60) -> SessionConfig:
    return SessionConfig(
        session_id="stop-on-cancel", work_dir=str(work_dir), timeout=timeout, sandbox_mode=sandbox_mode
    )


@contextlib.asynccontextmanager
async def _session(work_dir: Path, marker: str, **config: object) -> AsyncIterator[LocalPersistentSession]:
    """A started session; whatever a failing test leaves behind is removed."""
    session = LocalPersistentSession(_config(work_dir, **config))  # type: ignore[arg-type]
    await session.start()
    try:
        yield session
    finally:
        kill_marked(marker)
        await session.close()


@pytest.mark.asyncio
async def test_cancelling_the_token_stops_the_command_and_keeps_its_partial_output(tmp_path: Path) -> None:
    marker = "sleep 4711.1"
    token = CancellationToken("req-1")
    async with _session(tmp_path, marker) as session:
        running = asyncio.create_task(
            session.execute(f"echo started; bash -c '{marker}; echo never'", cancel_token=token)
        )
        await wait_until(lambda: process_alive(marker))

        token.cancel(CancelReason.USER_CANCELLED)
        async with asyncio.timeout(_SETTLE_S):
            result = await running

        assert result.success is False
        assert result.error is not None and result.error.startswith("Cancelled")
        assert "started" in result.stdout
        assert "never" not in result.stdout
        assert not process_alive(marker)


@pytest.mark.asyncio
async def test_the_next_command_runs_in_a_fresh_shell_after_a_cancel(tmp_path: Path) -> None:
    marker = "sleep 4711.2"
    token = CancellationToken("req-1")
    async with _session(tmp_path, marker) as session:
        assert (await session.execute("export KEEP=1")).success
        running = asyncio.create_task(session.execute(marker, cancel_token=token))
        await wait_until(lambda: process_alive(marker))
        token.cancel()
        await asyncio.wait_for(running, _SETTLE_S)

        follow_up = await session.execute('echo "[${KEEP:-fresh}]"')

        assert follow_up.success
        assert "[fresh]" in follow_up.stdout


@pytest.mark.asyncio
async def test_a_cancelled_command_is_never_run_a_second_time(tmp_path: Path) -> None:
    marker = "sleep 4711.3"
    token = CancellationToken("req-1")
    counter = tmp_path / "runs.txt"
    async with _session(tmp_path, marker) as session:
        running = asyncio.create_task(session.execute(f"echo run >> {counter}; {marker}", cancel_token=token))
        await wait_until(counter.exists)
        token.cancel()
        await asyncio.wait_for(running, _SETTLE_S)
        await session.execute("true")

        assert counter.read_text().splitlines() == ["run"]


@pytest.mark.asyncio
async def test_a_token_that_is_never_cancelled_changes_nothing(tmp_path: Path) -> None:
    async with _session(tmp_path, "sleep 4711.4") as session:
        result = await session.execute("echo fine", cancel_token=CancellationToken("req-1"))

        assert result.success
        assert "fine" in result.stdout


@pytest.mark.asyncio
async def test_cancelling_the_task_running_a_command_stops_the_command_and_leaves_a_usable_session(
    tmp_path: Path,
) -> None:
    marker = "sleep 4711.5"
    async with _session(tmp_path, marker) as session:
        running = asyncio.create_task(session.execute(f"bash -c '{marker}'"))
        await wait_until(lambda: process_alive(marker))

        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

        assert not process_alive(marker)
        follow_up = await session.execute("echo usable")
        assert follow_up.success
        assert "usable" in follow_up.stdout


@pytest.mark.asyncio
async def test_a_cancelled_stream_ends_with_a_cancelled_marker(tmp_path: Path) -> None:
    marker = "sleep 4711.6"
    token = CancellationToken("req-1")
    async with _session(tmp_path, marker) as session:
        chunks: list[str] = []

        async def consume() -> None:
            async for chunk in session.execute_stream(f"echo started; {marker}", cancel_token=token):
                chunks.append(chunk)

        consuming = asyncio.create_task(consume())
        await wait_until(lambda: process_alive(marker))
        token.cancel()
        await asyncio.wait_for(consuming, _SETTLE_S)

        text = "".join(chunks)
        assert "started" in text
        assert "[ERROR] Cancelled" in text
        assert not process_alive(marker)


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["cancel", "timeout"])
async def test_a_sandboxed_shell_leaves_no_orphaned_descendants(tmp_path: Path, how: str) -> None:
    """With a native sandbox the shell shares the server's process group; killing the group is not an option."""
    marker = {"cancel": "sleep 4711.71", "timeout": "sleep 4711.72"}[how]
    token = CancellationToken("req-1")
    async with _session(tmp_path, marker, sandbox_mode="auto") as session:
        if not session.is_sandboxed:
            pytest.skip("no native sandbox provider on this platform")
        command = f"bash -c '{marker}; echo never'"
        if how == "cancel":
            running = asyncio.create_task(session.execute(command, cancel_token=token))
            await wait_until(lambda: process_alive(marker))
            token.cancel()
            result = await asyncio.wait_for(running, _SETTLE_S)
        else:
            result = await session.execute(command, timeout=2)

        assert result.success is False
        assert not process_alive(marker)
        follow_up = await session.execute("echo usable")
        assert follow_up.success
