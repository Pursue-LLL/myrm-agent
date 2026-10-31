"""The Python tool keeps a bounded amount of what a script writes, and stops a script that never stops writing."""

from __future__ import annotations

import asyncio
import sys
import time
import tracemalloc
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.common import generate_wrapper_script
from myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess import (
    _pipe_limit,
    run_python_subprocess,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionResult
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from tests.support.marked_processes import kill_marked, process_alive

_MARKER = "flood_4711_9"
# The wrapper's cap on captured stdout characters; the pipes are read up to 12 times this plus 64 KiB (1,265,536 bytes).
_CAP = 100_000
_NOTE = "Output limit reached"

_NEVER_STOPS = {
    "stderr": "import sys\nwhile True:\n    sys.stderr.write('x' * 1023 + '\\n')\n",
    "logging": "import logging\nwhile True:\n    logging.warning('x' * 1000)\n",
    "fd": "import os\nwhile True:\n    os.write(1, b'x' * 65536)\n",
}


@pytest.fixture(autouse=True)
def _no_native_sandbox() -> Iterator[None]:
    """The sandbox wrapper is irrelevant to the output path and needs host-specific read grants."""
    with patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        return_value=(None, SandboxStatus(enabled=False, provider_name="null", reason="test")),
    ):
        yield
    kill_marked(_MARKER)


async def _run_script(tmp_path: Path, code: str, *, timeout: int = 30) -> ExecutionResult:
    """Run *code* through the production wrapper, the way the Python tool does."""
    code_file = tmp_path / "user_code.py"
    code_file.write_text(code, encoding="utf-8")
    wrapper = tmp_path / f"{_MARKER}_wrapper.py"
    wrapper.write_text(
        generate_wrapper_script(
            str(code_file), allow_network=True, timeout=None, memory_limit_mb=None, max_output_bytes=_CAP
        ),
        encoding="utf-8",
    )
    return await asyncio.wait_for(
        run_python_subprocess(
            script_path=wrapper,
            timeout=timeout,
            python_executable=sys.executable,
            cwd=tmp_path,
            max_output_bytes=_CAP,
        ),
        timeout=timeout + 20,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("flood", _NEVER_STOPS.values(), ids=_NEVER_STOPS.keys())
async def test_a_script_that_never_stops_writing_is_stopped_at_the_deadline_without_filling_memory(
    tmp_path: Path, flood: str
) -> None:
    tracemalloc.start()
    tracemalloc.reset_peak()
    started = time.monotonic()
    try:
        result = await _run_script(tmp_path, flood, timeout=2)
        peak_bytes = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert result.success is False
    assert "timed out" in (result.error or "")
    assert time.monotonic() - started < 8
    assert not process_alive(_MARKER)
    # Without a cap the host keeps every byte the script wrote during the two seconds (hundreds of MB).
    assert peak_bytes < 20 * 1024 * 1024


@pytest.mark.asyncio
async def test_stderr_beyond_the_cap_is_cut_and_the_result_still_arrives(tmp_path: Path) -> None:
    result = await _run_script(tmp_path, "import sys\nsys.stderr.write('e' * 20_000_000)\nprint('done')\n")

    assert result.success is True
    assert result.stdout.strip() == "done"
    assert _NOTE in result.stderr


@pytest.mark.asyncio
async def test_writes_to_the_stdout_pipe_beyond_the_cap_are_cut_with_a_note(tmp_path: Path) -> None:
    # Written to the file descriptor, they bypass the wrapper's own bound and fill the pipe ahead of its result.
    result = await _run_script(tmp_path, "import os\nos.write(1, b'x' * 3_000_000)\n")

    assert _NOTE in result.stderr
    assert len(result.stdout) <= _pipe_limit(_CAP)


@pytest.mark.asyncio
@pytest.mark.parametrize("char", ["a", "中", "\U0001f600"], ids=["ascii", "bmp", "outside-bmp"])
async def test_output_at_the_wrappers_cap_is_delivered_whole(tmp_path: Path, char: str) -> None:
    # json.dumps spells a character outside the BMP with 12 bytes, so the pipe cap must leave room for that.
    result = await _run_script(tmp_path, f"import sys\nsys.stdout.write({char!r} * {_CAP})\n")

    assert result.success is True
    assert result.stdout == char * _CAP
    assert _NOTE not in result.stderr
