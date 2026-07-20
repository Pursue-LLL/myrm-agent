"""Unit tests for SandboxedPythonCondition.

Validates script execution, SKIP signals, timeout behavior, and context injection.
"""

from unittest.mock import MagicMock

import pytest

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
async def test_script_error_returns_false():
    condition = SandboxedPythonCondition(timeout_seconds=5)
    should_run, ctx = await condition.evaluate(_make_job("raise ValueError('boom')"))
    assert should_run is False
    assert "Probe Failed" in ctx


@pytest.mark.asyncio
async def test_timeout_returns_false():
    condition = SandboxedPythonCondition(timeout_seconds=1)
    should_run, ctx = await condition.evaluate(_make_job("import time; time.sleep(10)"))
    assert should_run is False
    assert "Timeout" in ctx


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
