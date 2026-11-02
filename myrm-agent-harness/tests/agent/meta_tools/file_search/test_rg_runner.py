"""Tests for _rg_runner — ripgrep subprocess lifecycle.

Covers:
- Early stop returns promptly even when unread output far exceeds the stream buffer
- Full consumption, exit codes and stderr capture
- Timeout and cancellation both reap the child
- stdin is closed and cwd is honored
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search._rg_runner import RgRunResult, run_rg

# 600 KB written in one go: the child has already produced everything by the time the reader stops, so
# the unread output exceeds asyncio's stream buffer while the child is gone. Stopping without draining
# leaves the stream paused and ``Process.wait()`` pending (reproduced on macOS).
_BURST_SCRIPT = "import sys\nsys.stdout.write(('x' * 99 + '\\n') * 6000)\n"
# A producer that keeps writing roughly 8 MB until it is terminated.
_FLOOD_SCRIPT = "import sys\nfor i in range(300000):\n    sys.stdout.write(f'line-{i:07d}-padding-padding\\n')\n"
_PID_THEN_SLEEP_SCRIPT = "import os, sys, time\nprint(os.getpid(), flush=True)\ntime.sleep(60)\n"


def _python(script: str) -> list[str]:
    return [sys.executable, "-c", script]


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
