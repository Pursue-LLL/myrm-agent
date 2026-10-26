"""``spawn_cli_process`` against real subprocesses: lines, stderr, and every way a turn can stop its process."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import textwrap
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli import process as process_module
from myrm_agent_harness.toolkits.acp.runtime.cli.process import CliLaunchError, CliProcess, spawn_cli_process

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups and signals")

_ENV = dict(os.environ)


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", textwrap.dedent(code)]


def _spawn(code: str, *, stdin_text: str | None = None):
    return spawn_cli_process(_python(code), env=_ENV, cwd=os.getcwd(), stdin_text=stdin_text)


async def _collect(process: CliProcess) -> list[str]:
    return [line async for line in process.lines()]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _until_gone(pid: int) -> bool:
    async with asyncio.timeout(10):
        while _alive(pid):
            await asyncio.sleep(0.05)
    return True


class TestLines:
    @pytest.mark.asyncio
    async def test_lines_arrive_without_blanks_and_the_exit_code_is_reported(self) -> None:
        async with _spawn("print('one'); print(); print('  two  ')") as process:
            lines = await _collect(process)
            code = await process.wait()

        assert lines == ["one", "two"]
        assert code == 0
        assert process.returncode == 0
        assert process.killed_by_us is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("size", [100_000, 3_000_000])
    async def test_a_single_line_far_beyond_the_default_stream_limit_arrives_intact(self, size: int) -> None:
        """A tool result can be a whole file on one NDJSON line; asyncio's 64 KiB default used to fail the turn."""
        async with _spawn(f"print('x' * {size})") as process:
            lines = await _collect(process)

        assert [len(line) for line in lines] == [size]

    @pytest.mark.asyncio
    async def test_the_prompt_reaches_stdin(self) -> None:
        async with _spawn("import sys; print(sys.stdin.read().strip())", stdin_text="hello prompt") as process:
            lines = await _collect(process)

        assert lines == ["hello prompt"]

    @pytest.mark.asyncio
    async def test_a_process_that_leaves_before_reading_its_prompt_is_not_an_error(self) -> None:
        async with _spawn("pass", stdin_text="x" * 2_000_000) as process:
            assert await _collect(process) == []
            assert await process.wait() == 0

    @pytest.mark.asyncio
    async def test_undecodable_bytes_are_replaced(self) -> None:
        async with _spawn("import sys; sys.stdout.buffer.write(b'bad \\xff byte\\n')") as process:
            lines = await _collect(process)

        assert lines == ["bad \ufffd byte"]


class TestStderr:
    @pytest.mark.asyncio
    async def test_stderr_is_collected_for_the_verdict(self) -> None:
        async with _spawn("import sys; sys.stderr.write('boom\\n'); sys.exit(2)") as process:
            await _collect(process)
            code = await process.wait()

        assert code == 2
        assert process.stderr_text == "boom"

    @pytest.mark.asyncio
    async def test_only_the_tail_of_a_flood_is_kept(self) -> None:
        code = "import sys; sys.stderr.write('a' * 100000 + 'THE-END')"
        async with _spawn(code) as process:
            await _collect(process)
            await process.wait()

        assert len(process.stderr_text) <= 8 * 1024
        assert process.stderr_text.endswith("THE-END")

    @pytest.mark.asyncio
    async def test_a_grandchild_holding_stderr_open_does_not_hold_the_turn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(process_module, "_STDERR_DRAIN_SECONDS", 0.3)
        code = """
            import subprocess, sys
            subprocess.Popen(["sleep", "30"], stdout=subprocess.DEVNULL)
            print("parent done", flush=True)
        """
        async with _spawn(code) as process:
            await _collect(process)
            async with asyncio.timeout(5):
                assert await process.wait() == 0

    @pytest.mark.asyncio
    async def test_waiting_before_the_exit_is_not_held_by_a_grandchild_either(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``wait()`` is already pending while the CLI is alive: asyncio would keep it pending until the grandchild ends."""
        monkeypatch.setattr(process_module, "_STDERR_DRAIN_SECONDS", 0.3)
        code = """
            import subprocess, time
            subprocess.Popen(["sleep", "30"], stdout=subprocess.DEVNULL)
            time.sleep(0.5)
        """
        async with _spawn(code) as process:
            async with asyncio.timeout(5):
                assert await process.wait() == 0


class TestStopping:
    @pytest.mark.asyncio
    async def test_terminate_stops_a_running_process_and_says_who_did_it(self) -> None:
        async with _spawn("import time; time.sleep(60)") as process:
            await process.terminate()

            assert process.returncode == -signal.SIGTERM
            assert process.killed_by_us is True

    @pytest.mark.asyncio
    async def test_terminate_is_idempotent_and_safe_after_exit(self) -> None:
        async with _spawn("import time; time.sleep(60)") as process:
            await asyncio.gather(process.terminate(), process.terminate())
            await process.terminate()

        async with _spawn("pass") as finished:
            await _collect(finished)
            await finished.wait()
            await finished.terminate()
            assert finished.killed_by_us is False

    @pytest.mark.asyncio
    async def test_a_process_that_ignores_sigterm_is_killed_after_the_grace_period(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(process_module, "_TERMINATE_GRACE_SECONDS", 0.3)
        code = """
            import signal, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            print("ready", flush=True)
            time.sleep(60)
        """
        async with _spawn(code) as process:
            async for _ in process.lines():
                break
            await process.terminate()

            assert process.returncode == -signal.SIGKILL

    @pytest.mark.asyncio
    async def test_the_whole_process_group_goes_with_the_cli(self, tmp_path: Path) -> None:
        """A CLI's tool subprocesses must not outlive a stopped turn."""
        pid_file = tmp_path / "grandchild.pid"
        code = f"""
            import subprocess, time
            child = subprocess.Popen(["sleep", "60"])
            open({str(pid_file)!r}, "w").write(str(child.pid))
            print("spawned", flush=True)
            time.sleep(60)
        """
        async with _spawn(code) as process:
            async for _ in process.lines():
                break
            grandchild = int(pid_file.read_text())
            assert _alive(grandchild)

            await process.terminate()

            assert await _until_gone(grandchild)

    @pytest.mark.asyncio
    async def test_leaving_the_context_stops_a_process_that_is_still_running(self) -> None:
        with pytest.raises(RuntimeError, match="consumer failed"):
            async with _spawn("import time; time.sleep(60)") as process:
                pid = process._process.pid
                raise RuntimeError("consumer failed")

        assert process.returncode is not None
        assert process.killed_by_us is True
        assert not _alive(pid)

    @pytest.mark.asyncio
    async def test_a_cancelled_consumer_still_stops_its_process(self) -> None:
        """Stop pressed while the CLI is silent: the task awaiting its output is cancelled."""
        started = asyncio.Event()
        holder: list[CliProcess] = []

        async def consume() -> None:
            async with _spawn("import time; time.sleep(60)") as process:
                holder.append(process)
                started.set()
                await _collect(process)

        task = asyncio.create_task(consume())
        await started.wait()
        pid = holder[0]._process.pid
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert holder[0].returncode is not None
        assert holder[0].killed_by_us is True
        assert not _alive(pid)

    @pytest.mark.asyncio
    async def test_cancelling_again_during_the_stop_does_not_leave_it_half_done(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(process_module, "_TERMINATE_GRACE_SECONDS", 0.5)
        code = """
            import signal, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            print("ready", flush=True)
            time.sleep(60)
        """
        holder: list[CliProcess] = []
        ready = asyncio.Event()

        async def consume() -> None:
            async with _spawn(code) as process:
                holder.append(process)
                async for _ in process.lines():
                    ready.set()
                    await asyncio.sleep(60)

        task = asyncio.create_task(consume())
        await ready.wait()
        pid = holder[0]._process.pid
        task.cancel()
        await asyncio.sleep(0.1)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert await _until_gone(pid)

    @pytest.mark.asyncio
    async def test_signal_errors_from_a_vanished_group_are_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def gone(pid: int, sig: int) -> None:
            raise ProcessLookupError

        monkeypatch.setattr(process_module, "kill_process_group", gone)
        monkeypatch.setattr(process_module, "_TERMINATE_GRACE_SECONDS", 0.2)
        async with _spawn("import time; time.sleep(60)") as process:
            await process.terminate()
            assert process.killed_by_us is True
            process._process.kill()
            await process._process.wait()

    @pytest.mark.asyncio
    async def test_an_executable_that_does_not_exist_is_a_launch_error_naming_it(self) -> None:
        with pytest.raises(CliLaunchError, match="CLI executable not found: /nonexistent/agent"):
            async with spawn_cli_process(["/nonexistent/agent"], env=_ENV, cwd=os.getcwd(), stdin_text=None):
                pass

    @pytest.mark.asyncio
    async def test_a_working_directory_that_does_not_exist_is_not_a_launch_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            async with spawn_cli_process(_python("pass"), env=_ENV, cwd=str(tmp_path / "gone"), stdin_text=None):
                pass


class TestIdleTicks:
    @pytest.mark.asyncio
    async def test_a_silent_cli_ticks_and_its_lines_arrive_in_order(self) -> None:
        code = """
            import sys, time
            print("first", flush=True)
            time.sleep(0.5)
            print("second", flush=True)
        """
        async with _spawn(code) as process:
            items = [item async for item in process.lines(idle_tick=0.1)]

        assert [item for item in items if item is not None] == ["first", "second"]
        first, second = items.index("first"), items.index("second")
        assert items[first + 1 : second].count(None) >= 2
        assert None not in items[:first]

    @pytest.mark.asyncio
    async def test_a_tick_in_the_middle_of_a_line_does_not_split_it(self) -> None:
        code = """
            import sys, time
            sys.stdout.write("half of a ")
            sys.stdout.flush()
            time.sleep(0.5)
            sys.stdout.write("line\\n")
            sys.stdout.flush()
        """
        async with _spawn(code) as process:
            items = [item async for item in process.lines(idle_tick=0.1)]

        assert [item for item in items if item is not None] == ["half of a line"]
        assert items.count(None) >= 2

    @pytest.mark.asyncio
    async def test_without_a_tick_a_silent_cli_just_takes_its_time(self) -> None:
        code = """
            import time
            time.sleep(0.3)
            print("late", flush=True)
        """
        async with _spawn(code) as process:
            items = [item async for item in process.lines()]

        assert items == ["late"]
