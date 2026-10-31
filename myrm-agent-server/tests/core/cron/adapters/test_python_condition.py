"""Unit tests for SandboxedPythonCondition.

Validates script execution, SKIP signals, context injection, that a script which cannot reach a verdict
(crash, timeout, cannot start) raises ``PreFlightConditionError`` (only a verdict of "skip" returns False), and
that a deadline or a cancel stops the script together with its children, those in a session of their own,
and its background commands, even while it writes without end, and that output over 5 MiB fails the run.
"""

import asyncio
import shlex
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import psutil
import pytest
from myrm_agent_harness.toolkits.cron.protocols import PreFlightConditionError

from app.core.cron.adapters.python_condition import SandboxedPythonCondition

# The documented limit on what a script may write; the adapter fails the run past it.
_MAX_OUTPUT_BYTES = 5 * 1024 * 1024


def _make_job(script: str | None = None) -> MagicMock:
    job = MagicMock()
    job.id = "test-job-001"
    job.pre_condition_script = script
    return job


def _is_running(pid: int) -> bool:
    """A process that exited but is not reaped yet is not running."""
    try:
        return bool(psutil.Process(pid).status() != psutil.STATUS_ZOMBIE)
    except psutil.NoSuchProcess:
        return False


@pytest.mark.asyncio
async def test_no_script_returns_true() -> None:
    condition = SandboxedPythonCondition()
    should_run, ctx = await condition.evaluate(_make_job(None))
    assert should_run is True
    assert ctx == ""


@pytest.mark.asyncio
async def test_empty_script_returns_true() -> None:
    condition = SandboxedPythonCondition()
    should_run, ctx = await condition.evaluate(_make_job("   "))
    assert should_run is True
    assert ctx == ""


@pytest.mark.asyncio
async def test_script_stdout_injected_as_context() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("print('hello world')"))
    assert should_run is True
    assert ctx == "hello world"


@pytest.mark.asyncio
async def test_skip_signal_string() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("print('[SKIP]')"))
    assert should_run is False
    assert ctx == ""


@pytest.mark.asyncio
async def test_skip_signal_json() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    script = 'import json; print(json.dumps({"action": "skip"}))'
    should_run, ctx = await condition.evaluate(_make_job(script))
    assert should_run is False
    assert ctx == ""


@pytest.mark.asyncio
async def test_a_crashing_script_fails_the_run_with_the_exception_line() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job("raise ValueError('boom')"))
    assert str(raised.value) == "exit code 1: ValueError: boom"


@pytest.mark.asyncio
async def test_a_failure_without_stderr_names_only_the_exit_code() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job("import sys; sys.exit(3)"))
    assert str(raised.value) == "exit code 3"


@pytest.mark.asyncio
async def test_the_failure_reason_is_free_of_credentials() -> None:
    secret = "sk-proj-" + "A1b2C3d4E5f6G7h8" * 3
    script = f"raise RuntimeError('all_sources_failed: coingecko: Authorization: Bearer {secret}')"
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job(script))
    assert secret not in str(raised.value)
    assert str(raised.value).startswith("exit code 1: RuntimeError: all_sources_failed: coingecko:")


@pytest.mark.asyncio
async def test_the_failure_reason_is_one_bounded_line() -> None:
    script = "import sys; sys.stderr.write('first line\\n' + 'x' * 5000 + '\\n'); sys.exit(1)"
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job(script))
    reason = str(raised.value).removeprefix("exit code 1: ")
    assert "\n" not in reason and "first line" not in reason
    assert len(reason) == 300 and reason.endswith("…")


@pytest.mark.asyncio
async def test_a_script_that_times_out_fails_the_run_and_is_killed(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = f"import os, time\nwith open({str(pid_file)!r}, 'w') as f:\n    f.write(str(os.getpid()))\ntime.sleep(30)\n"
    condition = SandboxedPythonCondition(timeout_seconds=2)
    with pytest.raises(PreFlightConditionError, match=r"^timed out after 2s$"):
        await condition.evaluate(_make_job(script))
    assert not _is_running(int(pid_file.read_text()))


@pytest.mark.asyncio
async def test_a_timeout_returns_on_time_and_stops_everything_the_script_started(tmp_path: Path) -> None:
    # Each child reports its pid and would run for 30 s, ten times the deadline.
    child = tmp_path / "child.py"
    child.write_text("import os, sys, time\nopen(sys.argv[1], 'w').write(str(os.getpid()))\ntime.sleep(30)\n")

    def argv(pid_file: Path) -> list[str]:
        return [sys.executable, str(child), str(pid_file)]

    # How scripts run commands: `subprocess.run` and `os.system` hand the child the script's own output pipes, a child
    # that starts a session of its own is out of the script's process group, and a command sent to the background
    # is adopted by init once the shell that started it exits, while the script keeps running. A script that never
    # stops writing is stopped while its pipes are still being emptied.
    scripts = {
        "subprocess.run": lambda p: f"import subprocess\nsubprocess.run({argv(p)!r})\n",
        "os.system": lambda p: f"import os\nos.system({shlex.join(argv(p))!r})\n",
        "own-session": lambda p: (
            f"import subprocess, time\nsubprocess.Popen({argv(p)!r}, start_new_session=True)\ntime.sleep(60)\n"
        ),
        "background": lambda p: f"import os, time\nos.system({shlex.join(argv(p)) + ' &'!r})\ntime.sleep(60)\n",
        "flood": lambda p: (
            f"import os, sys\nopen({str(p)!r}, 'w').write(str(os.getpid()))\nwhile True:\n    sys.stdout.write('x' * 1023 + '\\n')\n"
        ),
    }
    pid_files = {name: tmp_path / f"{name}.pid" for name in scripts}

    async def run(name: str) -> float:
        started = time.monotonic()
        with pytest.raises(PreFlightConditionError, match=r"^timed out after 3s$"):
            await SandboxedPythonCondition(timeout_seconds=3).evaluate(_make_job(scripts[name](pid_files[name])))
        return time.monotonic() - started

    elapsed = dict(zip(scripts, await asyncio.gather(*(run(name) for name in scripts)), strict=True))

    for name, seconds in elapsed.items():
        assert seconds < 10, f"{name}: returned after {seconds:.1f}s against a 3s deadline"
        assert not _is_running(int(pid_files[name].read_text())), f"{name}: the child is still running"


@pytest.mark.asyncio
async def test_a_cancelled_probe_stops_its_script(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = f"import os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\ntime.sleep(30)\n"
    task = asyncio.create_task(SandboxedPythonCondition(timeout_seconds=60).evaluate(_make_job(script)))
    async with asyncio.timeout(10):
        while not (pid_file.exists() and pid_file.read_text()):
            await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not _is_running(int(pid_file.read_text()))


@pytest.mark.asyncio
async def test_output_over_the_cap_fails_the_run_even_when_it_ends_with_a_skip() -> None:
    # The verdict is the last line, which a cut would drop and so turn a skip into a run.
    script = (
        f"import json, sys\nsys.stdout.write('x' * {_MAX_OUTPUT_BYTES + 1000} + '\\n')\nprint(json.dumps({{'action': 'skip'}}))\n"
    )
    with pytest.raises(PreFlightConditionError, match=r"^wrote more than 5 MiB of output$"):
        await SandboxedPythonCondition(timeout_seconds=30).evaluate(_make_job(script))


@pytest.mark.asyncio
async def test_output_of_exactly_the_cap_is_injected_whole() -> None:
    # `print` adds the newline, which the context does not keep.
    script = f"print('x' * {_MAX_OUTPUT_BYTES - 1})"
    should_run, ctx = await SandboxedPythonCondition(timeout_seconds=30).evaluate(_make_job(script))
    assert should_run is True
    assert ctx == "x" * (_MAX_OUTPUT_BYTES - 1)


@pytest.mark.asyncio
async def test_a_script_that_cannot_start_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    async def cannot_start(*args: object, **kwargs: object) -> None:
        raise OSError("exec format error at /private/tmp/secret-path")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", cannot_start)
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job("print('x')"))
    assert str(raised.value) == "could not run the script (OSError)"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "script",
    ["print('ok')", "raise ValueError('boom')", "import sys; sys.exit(3)"],
    ids=["verdict", "crash", "exit-code"],
)
async def test_no_script_file_is_left_behind(script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    condition = SandboxedPythonCondition(timeout_seconds=5)
    try:
        await condition.evaluate(_make_job(script))
    except PreFlightConditionError:
        pass
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_custom_timeout_parameter() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=60)
    assert condition.timeout_seconds == 60


@pytest.mark.asyncio
async def test_multiline_stdout_full_injection() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    script = "print('line1')\nprint('line2')\nprint('line3')"
    should_run, ctx = await condition.evaluate(_make_job(script))
    assert should_run is True
    assert "line1" in ctx
    assert "line2" in ctx
    assert "line3" in ctx


@pytest.mark.asyncio
async def test_empty_stdout_returns_empty_context() -> None:
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("x = 1"))
    assert should_run is True
    assert ctx == ""
