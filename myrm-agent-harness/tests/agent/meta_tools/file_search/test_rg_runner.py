"""Tests for _rg_runner — ripgrep subprocess lifecycle.

Covers:
- Early stop returns promptly even when unread output far exceeds the stream buffer, on every platform
- Output lines far longer than asyncio's default stream limit are delivered; beyond the limit the run fails cleanly
- A line can end at a NUL byte instead of a line feed, with the same early stop and the same limit
- Full consumption, exit codes and stderr capture
- Timeout and cancellation both reap the child
- stdin is closed and cwd is honored
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import _rg_runner
from myrm_agent_harness.agent.meta_tools.file_search._rg_runner import RgRunResult, run_rg

# 600 KB written in one go: the child has already produced everything by the time the reader stops, so
# the unread output exceeds asyncio's stream buffer while the child is gone. Stopping without draining
# leaves the stream paused and ``Process.wait()`` pending. A real child shows this on macOS only: on Linux
# (Ubuntu 24.04, Python 3.13) the same run returns in milliseconds without the drain, which is why
# ``TestEarlyStopContract`` pins the drain with a fake process on every platform.
_BURST_SCRIPT = "import sys\nsys.stdout.write(('x' * 99 + '\\n') * 6000)\n"
# A producer that keeps writing roughly 8 MB until it is terminated.
_FLOOD_SCRIPT = "import sys\nfor i in range(300000):\n    sys.stdout.write(f'line-{i:07d}-padding-padding\\n')\n"
_PID_THEN_SLEEP_SCRIPT = "import os, sys, time\nprint(os.getpid(), flush=True)\ntime.sleep(60)\n"
_PID_THEN_LONG_LINE_THEN_SLEEP_SCRIPT = (
    "import os, sys, time\n"
    "print(os.getpid(), flush=True)\n"
    "sys.stdout.write('y' * 100000 + '\\n')\n"
    "sys.stdout.flush()\n"
    "time.sleep(60)\n"
)
# A ``--null`` listing: every name ends with a NUL byte, and a name may hold a line break.
_NUL_LINES_SCRIPT = "import sys\nsys.stdout.buffer.write(b'a\\nb\\0c\\0')\n"
_UNTERMINATED_LAST_LINE_SCRIPT = "import sys\nsys.stdout.buffer.write(b'a\\0b')\n"
_NUL_FLOOD_SCRIPT = "import sys\nfor i in range(300000):\n    sys.stdout.write(f'name-{i:07d}-padding-padding\\0')\n"
_PID_THEN_LONG_NUL_LINE_THEN_SLEEP_SCRIPT = (
    "import os, sys, time\n"
    "sys.stdout.write(f'{os.getpid()}\\0')\n"
    "sys.stdout.write('y' * 100000 + '\\0')\n"
    "sys.stdout.flush()\n"
    "time.sleep(60)\n"
)


def _python(script: str) -> list[str]:
    return [sys.executable, "-c", script]


def _collect() -> tuple[list[bytes], Callable[[bytes], bool]]:
    """A list and the ``on_line`` callback that appends every line to it and never stops the run."""
    lines: list[bytes] = []

    def on_line(line: bytes) -> bool:
        lines.append(line)
        return False

    return lines, on_line


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _wait_until_gone(pid: int, timeout_seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return True
        await asyncio.sleep(0.05)
    return not _is_alive(pid)


class TestEarlyStop:
    @pytest.mark.parametrize(
        ("script", "repeats"),
        # The hang is a race against the child's exit; repeating makes a missing drain fail reliably.
        [(_BURST_SCRIPT, 6), (_FLOOD_SCRIPT, 1)],
        ids=["burst", "flood"],
    )
    async def test_returns_promptly_with_unread_output(self, tmp_path: Path, script: str, repeats: int) -> None:
        for _ in range(repeats):
            lines: list[bytes] = []

            def on_line(line: bytes, sink: list[bytes] = lines) -> bool:
                sink.append(line)
                return len(sink) >= 100

            started = time.monotonic()
            result = await run_rg(_python(script), cwd=tmp_path, timeout_seconds=3.0, on_line=on_line)

            assert len(lines) == 100
            assert result.stopped_early is True
            assert result.failed is False
            assert time.monotonic() - started < 2.0

    async def test_stops_on_first_line(self, tmp_path: Path) -> None:
        result = await run_rg(_python(_FLOOD_SCRIPT), cwd=tmp_path, timeout_seconds=3.0, on_line=lambda _line: True)
        assert result.stopped_early is True


class _FakeProcess:
    """Mirrors ``Process.wait()``: it completes only once the child has exited and its stdout reached end-of-stream."""

    def __init__(self, stdout: asyncio.StreamReader, stderr: asyncio.StreamReader) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int | None:
        while not self.stdout.at_eof():
            await asyncio.sleep(0.001)
        return self.returncode


class TestEarlyStopContract:
    """An early stop must drain the output nobody reads, or the exit is never observed.

    A real child shows the hang on some platforms only, so the contract is pinned with a fake process whose
    ``wait()`` has the same precondition everywhere.
    """

    async def test_unread_output_is_drained_so_the_exit_is_observed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stdout = asyncio.StreamReader(limit=1024)
        stdout.feed_data((b"x" * 99 + b"\n") * 6000)
        stdout.feed_eof()
        stderr = asyncio.StreamReader()
        stderr.feed_eof()

        async def spawn(*_args: object, **_kwargs: object) -> _FakeProcess:
            return _FakeProcess(stdout, stderr)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        seen: list[bytes] = []

        def on_line(line: bytes) -> bool:
            seen.append(line)
            return len(seen) >= 100

        result = await run_rg(["rg"], cwd=tmp_path, timeout_seconds=1.0, on_line=on_line)

        assert len(seen) == 100
        assert result.stopped_early is True


class TestLongLines:
    async def test_line_above_the_asyncio_default_limit_is_delivered(self, tmp_path: Path) -> None:
        """One JSON event holds a whole matching line, so a match inside a minified bundle is far above 64 KiB."""
        lines: list[bytes] = []

        def on_line(line: bytes) -> bool:
            lines.append(line)
            return False

        result = await run_rg(
            _python("import sys\nsys.stdout.write('x' * 1_000_000 + '\\n')\n"),
            cwd=tmp_path,
            timeout_seconds=10.0,
            on_line=on_line,
        )

        assert [len(line) for line in lines] == [1_000_001]
        assert result.failed is False

    async def test_line_beyond_the_limit_raises_value_error_and_kills_the_child(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_rg_runner, "_STREAM_LIMIT_BYTES", 4096)
        pids: list[int] = []

        def on_line(line: bytes) -> bool:
            pids.append(int(line))
            return False

        with pytest.raises(ValueError):
            await run_rg(
                _python(_PID_THEN_LONG_LINE_THEN_SLEEP_SCRIPT), cwd=tmp_path, timeout_seconds=10.0, on_line=on_line
            )

        assert await _wait_until_gone(pids[0])


class TestLineTerminator:
    """A name listed with ``--null`` can hold a line break, so the caller picks the byte that ends a line."""

    async def test_a_line_ends_at_the_terminator_not_at_a_line_break(self, tmp_path: Path) -> None:
        lines, on_line = _collect()

        result = await run_rg(
            _python(_NUL_LINES_SCRIPT), cwd=tmp_path, timeout_seconds=10.0, on_line=on_line, line_terminator=b"\0"
        )

        assert lines == [b"a\nb\0", b"c\0"]
        assert result.failed is False

    async def test_the_last_line_may_lack_its_terminator(self, tmp_path: Path) -> None:
        lines, on_line = _collect()

        await run_rg(
            _python(_UNTERMINATED_LAST_LINE_SCRIPT),
            cwd=tmp_path,
            timeout_seconds=10.0,
            on_line=on_line,
            line_terminator=b"\0",
        )

        assert lines == [b"a\0", b"b"]

    async def test_stops_early_between_terminated_lines(self, tmp_path: Path) -> None:
        lines: list[bytes] = []

        def on_line(line: bytes) -> bool:
            lines.append(line)
            return len(lines) >= 100

        started = time.monotonic()
        result = await run_rg(
            _python(_NUL_FLOOD_SCRIPT), cwd=tmp_path, timeout_seconds=3.0, on_line=on_line, line_terminator=b"\0"
        )

        assert len(lines) == 100
        assert result.stopped_early is True
        assert time.monotonic() - started < 2.0

    async def test_line_beyond_the_limit_raises_value_error_and_kills_the_child(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_rg_runner, "_STREAM_LIMIT_BYTES", 4096)
        pids: list[int] = []

        def on_line(line: bytes) -> bool:
            pids.append(int(line.removesuffix(b"\0")))
            return False

        with pytest.raises(ValueError):
            await run_rg(
                _python(_PID_THEN_LONG_NUL_LINE_THEN_SLEEP_SCRIPT),
                cwd=tmp_path,
                timeout_seconds=10.0,
                on_line=on_line,
                line_terminator=b"\0",
            )

        assert await _wait_until_gone(pids[0])


class TestFullRun:
    async def test_consumes_every_line(self, tmp_path: Path) -> None:
        lines: list[bytes] = []

        def on_line(line: bytes) -> bool:
            lines.append(line)
            return False

        result = await run_rg(
            _python("for i in range(1000):\n    print(i)\n"),
            cwd=tmp_path,
            timeout_seconds=10.0,
            on_line=on_line,
        )

        assert len(lines) == 1000
        assert result == RgRunResult(returncode=0, stderr="", stopped_early=False)

    @pytest.mark.parametrize(("code", "failed"), [(0, False), (1, False), (2, True), (127, True)])
    async def test_exit_code_classification(self, tmp_path: Path, code: int, failed: bool) -> None:
        result = await run_rg(
            _python(f"import sys\nsys.exit({code})\n"),
            cwd=tmp_path,
            timeout_seconds=10.0,
            on_line=lambda _line: False,
        )
        assert result.returncode == code
        assert result.failed is failed

    async def test_captures_stderr(self, tmp_path: Path) -> None:
        result = await run_rg(
            _python("import sys\nsys.stderr.write('boom: bad glob')\nsys.exit(2)\n"),
            cwd=tmp_path,
            timeout_seconds=10.0,
            on_line=lambda _line: False,
        )
        assert "boom: bad glob" in result.stderr
        assert result.failed is True


class TestProcessEnvironment:
    async def test_cwd_is_honored(self, tmp_path: Path) -> None:
        lines: list[bytes] = []

        def on_line(line: bytes) -> bool:
            lines.append(line)
            return False

        await run_rg(
            _python("import os\nprint(os.getcwd())\n"),
            cwd=tmp_path,
            timeout_seconds=10.0,
            on_line=on_line,
        )
        assert Path(lines[0].decode().strip()).resolve() == tmp_path.resolve()

    async def test_stdin_is_closed(self, tmp_path: Path) -> None:
        """A child reading stdin must see EOF immediately instead of waiting on the parent's terminal."""
        lines: list[bytes] = []

        def on_line(line: bytes) -> bool:
            lines.append(line)
            return False

        await asyncio.wait_for(
            run_rg(
                _python("import sys\nprint(repr(sys.stdin.read()))\n"),
                cwd=tmp_path,
                timeout_seconds=10.0,
                on_line=on_line,
            ),
            timeout=5.0,
        )
        assert lines == [b"''\n"]


class TestReaping:
    async def test_timeout_kills_child(self, tmp_path: Path) -> None:
        pids: list[int] = []

        def on_line(line: bytes) -> bool:
            pids.append(int(line))
            return False

        with pytest.raises(TimeoutError):
            await run_rg(_python(_PID_THEN_SLEEP_SCRIPT), cwd=tmp_path, timeout_seconds=1.0, on_line=on_line)

        assert len(pids) == 1
        assert await _wait_until_gone(pids[0])

    async def test_cancellation_kills_child(self, tmp_path: Path) -> None:
        pids: list[int] = []
        seen = asyncio.Event()

        def on_line(line: bytes) -> bool:
            pids.append(int(line))
            seen.set()
            return False

        task = asyncio.create_task(
            run_rg(_python(_PID_THEN_SLEEP_SCRIPT), cwd=tmp_path, timeout_seconds=30.0, on_line=on_line)
        )
        await asyncio.wait_for(seen.wait(), timeout=10.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert await _wait_until_gone(pids[0])
