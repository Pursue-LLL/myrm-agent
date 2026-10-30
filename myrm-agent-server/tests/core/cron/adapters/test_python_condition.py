"""Unit tests for SandboxedPythonCondition.

Validates script execution, SKIP signals, context injection, and that a script which cannot reach a verdict
(crash, timeout, cannot start) raises ``PreFlightConditionError`` instead of reading as a skip.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import psutil
import pytest
from myrm_agent_harness.toolkits.cron.protocols import PreFlightConditionError

from app.core.cron.adapters.python_condition import SandboxedPythonCondition


def _make_job(script: str | None = None) -> MagicMock:
    job = MagicMock()
    job.id = "test-job-001"
    job.pre_condition_script = script
    return job


@pytest.mark.asyncio
async def test_no_script_returns_true():
    condition = SandboxedPythonCondition()
    should_run, ctx = await condition.evaluate(_make_job(None))
    assert should_run is True
    assert ctx == ""


@pytest.mark.asyncio
async def test_empty_script_returns_true():
    condition = SandboxedPythonCondition()
    should_run, ctx = await condition.evaluate(_make_job("   "))
    assert should_run is True
    assert ctx == ""


@pytest.mark.asyncio
async def test_script_stdout_injected_as_context():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("print('hello world')"))
    assert should_run is True
    assert ctx == "hello world"


@pytest.mark.asyncio
async def test_skip_signal_string():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("print('[SKIP]')"))
    assert should_run is False
    assert ctx == ""


@pytest.mark.asyncio
async def test_skip_signal_json():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    script = 'import json; print(json.dumps({"action": "skip"}))'
    should_run, ctx = await condition.evaluate(_make_job(script))
    assert should_run is False
    assert ctx == ""


@pytest.mark.asyncio
async def test_a_crashing_script_fails_the_run_with_the_exception_line():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job("raise ValueError('boom')"))
    assert str(raised.value) == "exit code 1: ValueError: boom"


@pytest.mark.asyncio
async def test_a_failure_without_stderr_names_only_the_exit_code():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job("import sys; sys.exit(3)"))
    assert str(raised.value) == "exit code 3"


@pytest.mark.asyncio
async def test_the_failure_reason_is_free_of_credentials():
    secret = "sk-proj-" + "A1b2C3d4E5f6G7h8" * 3
    script = f"raise RuntimeError('all_sources_failed: coingecko: Authorization: Bearer {secret}')"
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job(script))
    assert secret not in str(raised.value)
    assert str(raised.value).startswith("exit code 1: RuntimeError: all_sources_failed: coingecko:")


@pytest.mark.asyncio
async def test_the_failure_reason_is_one_bounded_line():
    script = "import sys; sys.stderr.write('first line\\n' + 'x' * 5000 + '\\n'); sys.exit(1)"
    condition = SandboxedPythonCondition(timeout_seconds=5)
    with pytest.raises(PreFlightConditionError) as raised:
        await condition.evaluate(_make_job(script))
    reason = str(raised.value).removeprefix("exit code 1: ")
    assert "\n" not in reason and "first line" not in reason
    assert len(reason) == 300 and reason.endswith("…")


@pytest.mark.asyncio
async def test_a_script_that_times_out_fails_the_run_and_is_killed(tmp_path: Path):
    pid_file = tmp_path / "pid"
    script = f"import os, time\nwith open({str(pid_file)!r}, 'w') as f:\n    f.write(str(os.getpid()))\ntime.sleep(30)\n"
    condition = SandboxedPythonCondition(timeout_seconds=2)
    with pytest.raises(PreFlightConditionError, match=r"^timed out after 2s$"):
        await condition.evaluate(_make_job(script))
    assert not psutil.pid_exists(int(pid_file.read_text()))


@pytest.mark.asyncio
async def test_a_script_that_cannot_start_fails_the_run(monkeypatch: pytest.MonkeyPatch):
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
async def test_no_script_file_is_left_behind(script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    condition = SandboxedPythonCondition(timeout_seconds=5)
    try:
        await condition.evaluate(_make_job(script))
    except PreFlightConditionError:
        pass
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_custom_timeout_parameter():
    condition = SandboxedPythonCondition(timeout_seconds=60)
    assert condition.timeout_seconds == 60


@pytest.mark.asyncio
async def test_multiline_stdout_full_injection():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    script = "print('line1')\nprint('line2')\nprint('line3')"
    should_run, ctx = await condition.evaluate(_make_job(script))
    assert should_run is True
    assert "line1" in ctx
    assert "line2" in ctx
    assert "line3" in ctx


@pytest.mark.asyncio
async def test_empty_stdout_returns_empty_context():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("x = 1"))
    assert should_run is True
    assert ctx == ""
