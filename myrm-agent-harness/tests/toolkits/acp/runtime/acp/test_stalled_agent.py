"""A stalled ACP agent cannot hold up a stop: cancel and close end the agent and every process it started."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys
import time
from asyncio.subprocess import Process
from pathlib import Path

import psutil
import pytest

from myrm_agent_harness.toolkits.acp.runtime.acp import stalled_agent
from myrm_agent_harness.toolkits.acp.runtime.acp.runtime import AcpRuntime
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig

from ._fakes import make_png, make_pool, run_turn

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stalled agent is ended with a POSIX signal")

_STALLED_AGENT = Path(__file__).parent / "_stalled_acp_agent.py"
# Far longer than any wait below: an agent still asleep proves the stop did not wait for it.
_STALL_SECONDS = "60"
# The runtime's own loggers; the ACP SDK logs its failed send loop on the root logger, which is not ours to quiet.
_RUNTIME_LOGGERS = "myrm_agent_harness.toolkits.acp.runtime"


def _stalled_runtime(directory: Path, tool_pid_file: Path | None = None) -> tuple[AcpRuntime, str]:
    """A runtime over the stalled agent, and the 5 MiB image its turn carries.

    With ``tool_pid_file`` the agent starts a tool process that holds the same pipes and records its PID there.
    """
    image, _ = make_png(directory, "big.png", 5 * 1024 * 1024)
    runtime = AcpRuntime(
        "stalled",
        RuntimeConfig(
            backend_type="acp",
            command=sys.executable,
            args=[str(_STALLED_AGENT), _STALL_SECONDS, *([str(tool_pid_file)] if tool_pid_file else [])],
            cwd=str(directory),
            timeout_seconds=120,
        ),
    )
    return runtime, str(image)


async def _wait_until_stalled(runtime: AcpRuntime) -> Process:
    """The agent process, once its session exists and the 5 MiB prompt sits half written in its pipe."""
    deadline = time.monotonic() + 20
    while getattr(runtime, "_session_id", None) is None:
        assert time.monotonic() < deadline, "the agent never created a session"
        await asyncio.sleep(0.05)
    await asyncio.sleep(1.0)
    process = getattr(runtime, "_process", None)
    assert process is not None
    return process


async def _stalled_turn(
    directory: Path, tool_pid_file: Path | None = None
) -> tuple[AcpRuntime, asyncio.Task[None], Process]:
    """A turn whose prompt sits half written in the pipe of an agent that no longer reads it."""
    runtime, image = _stalled_runtime(directory, tool_pid_file)

    async def consume() -> None:
        async for _ in runtime.run_turn("look", "chat-1", images=[image]):
            pass

    turn = asyncio.create_task(consume())
    return runtime, turn, await _wait_until_stalled(runtime)


def _tool_running(pid: int) -> bool:
    """Whether the tool process still runs; one that was killed and not yet reaped does not count."""
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


async def _tool_ended(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while _tool_running(pid):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.05)
    return True


def _end_tool(pid: int) -> None:
    with contextlib.suppress(psutil.NoSuchProcess):
        psutil.Process(pid).kill()


async def _finish(runtime: AcpRuntime, turn: asyncio.Task[None], process: Process) -> None:
    turn.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await asyncio.wait_for(turn, timeout=20)
    with contextlib.suppress(ProcessLookupError):
        process.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(runtime.close(), timeout=20)


class TestStalledAgent:
    @pytest.mark.asyncio
    async def test_cancel_ends_an_agent_that_stopped_reading_a_large_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        runtime, turn, process = await _stalled_turn(tmp_path)
        try:
            started = time.monotonic()
            await asyncio.wait_for(runtime.cancel("chat-1"), timeout=20)
            await asyncio.wait_for(process.wait(), timeout=10)

            assert time.monotonic() - started < 10
            assert process.returncode in (-signal.SIGTERM, -signal.SIGKILL)
        finally:
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_cancel_ends_the_tool_process_the_agent_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        pid_file = tmp_path / "tool.pid"
        runtime, turn, process = await _stalled_turn(tmp_path, pid_file)
        tool = int(pid_file.read_text())
        try:
            await asyncio.wait_for(runtime.cancel("chat-1"), timeout=20)

            assert await _tool_ended(tool)
        finally:
            _end_tool(tool)
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_close_ends_the_tool_process_the_agent_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        pid_file = tmp_path / "tool.pid"
        runtime, turn, process = await _stalled_turn(tmp_path, pid_file)
        tool = int(pid_file.read_text())
        try:
            turn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(turn, timeout=20)
            await asyncio.wait_for(runtime.close(), timeout=20)

            assert process.returncode is not None
            assert await _tool_ended(tool)
        finally:
            _end_tool(tool)
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_a_consumer_that_stops_at_the_first_event_after_the_agent_was_ended_closes_the_turn_cleanly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        runtime, image = _stalled_runtime(tmp_path)
        stopped = asyncio.Event()

        async def consume() -> None:
            # The delegation stream's loop: once the stop token has tripped, the next event ends it and closes the turn.
            async with contextlib.aclosing(runtime.run_turn("look", "chat-1", images=[image])) as events:
                async for _ in events:
                    if stopped.is_set():
                        break

        turn = asyncio.create_task(consume())
        process = await _wait_until_stalled(runtime)
        try:
            stopped.set()
            with caplog.at_level(logging.ERROR):
                await asyncio.wait_for(runtime.cancel("chat-1"), timeout=20)
                await asyncio.wait_for(turn, timeout=20)

            assert process.returncode is not None
            assert [r.getMessage() for r in caplog.records if r.name.startswith(_RUNTIME_LOGGERS)] == []
        finally:
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_close_ends_an_agent_that_stopped_reading_a_large_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        runtime, turn, process = await _stalled_turn(tmp_path)
        try:
            turn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(turn, timeout=20)
            started = time.monotonic()
            await asyncio.wait_for(runtime.close(), timeout=20)

            assert time.monotonic() - started < 10
            assert process.returncode is not None
        finally:
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_a_healthy_agent_is_not_ended_by_cancel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        pool = make_pool(tmp_path, "--images")
        try:
            await run_turn(pool, [])
            runtime = pool.get("mock")
            process = getattr(runtime, "_process", None)
            assert process is not None

            await runtime.cancel("chat-1")
            await asyncio.sleep(0.2)

            assert process.returncode is None
        finally:
            await pool.close_all()
