"""A failure of the Python executor itself is logged with its stack and never printed to the process's stderr."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess import run_python_subprocess

_LOGGER_NAME = "myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess"


@pytest.mark.asyncio
async def test_a_failure_before_the_script_runs_is_logged_with_its_stack_and_not_printed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    probe_failure = OSError("sandbox probe failed")

    with (
        patch("myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider", side_effect=probe_failure),
        caplog.at_level(logging.ERROR, logger=_LOGGER_NAME),
    ):
        result = await run_python_subprocess(
            script_path=tmp_path / "wrapper.py",
            timeout=5,
            python_executable=sys.executable,
            cwd=tmp_path,
            max_output_bytes=1_000,
        )

    assert result.success is False
    assert result.error == "OSError: sandbox probe failed"
    assert [r.exc_info[1] for r in caplog.records if r.name == _LOGGER_NAME and r.exc_info] == [probe_failure]
    assert capsys.readouterr().err == ""
