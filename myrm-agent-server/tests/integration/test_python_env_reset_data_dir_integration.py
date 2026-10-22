"""Integration: the reset marker and the agent's Python environment find each other through MYRM_DATA_DIR alone.

The server derives the marker location from its state directory and the harness derives the environment location from
the same variable, each on its own. Only fresh interpreters with nothing but that variable set show whether they
agree the way a sandbox container does, so the two process starts below share no state and mock nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.allow_blocking_io]

_SERVER_DIR = Path(__file__).resolve().parents[2]
_PROCESS_TIMEOUT_SECONDS = 180

_REQUEST_AND_POLLUTE = """
import asyncio, json, os
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.config import get_execution_config
from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import VenvManager

from app.services.infra.python_env_reset import request_python_env_reset

data_dir = Path(os.environ["MYRM_DATA_DIR"]).resolve()
python = asyncio.run(VenvManager(get_execution_config()).get_python_executable())
(data_dir / "venvs" / "installed-by-agent.txt").write_text("package")
print(json.dumps({"placed": request_python_env_reset(), "python_under_data_dir": Path(python).is_relative_to(data_dir)}))
"""

_START_AND_REBUILD = """
import asyncio, json, os, subprocess
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.config import get_execution_config
from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import VenvManager

from app.services.infra.python_env_reset import apply_pending_python_env_reset

data_dir = Path(os.environ["MYRM_DATA_DIR"]).resolve()
removed = apply_pending_python_env_reset()
state = {
    "removed": removed,
    "environment_exists": (data_dir / "venvs").exists(),
    "marker_exists": (data_dir / "locks" / "python-env-reset").exists(),
}
python = asyncio.run(VenvManager(get_execution_config()).get_python_executable())
state["python_under_data_dir"] = Path(python).is_relative_to(data_dir)
state["agent_package_survived"] = (data_dir / "venvs" / "installed-by-agent.txt").exists()
state["interpreter_output"] = subprocess.run([python, "-c", "print(6 * 7)"], capture_output=True, text=True).stdout.strip()
print(json.dumps(state))
"""


def _run_in_fresh_interpreter(script: str, data_dir: Path) -> dict[str, object]:
    env = {**os.environ, "MYRM_DATA_DIR": str(data_dir), "HOME": str(data_dir / "home")}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    state: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])
    return state


def test_marker_left_by_one_process_resets_the_environment_of_the_next(tmp_path: Path) -> None:
    before_restart = _run_in_fresh_interpreter(_REQUEST_AND_POLLUTE, tmp_path)
    assert before_restart == {"placed": True, "python_under_data_dir": True}

    after_restart = _run_in_fresh_interpreter(_START_AND_REBUILD, tmp_path)

    assert after_restart == {
        "removed": True,
        "environment_exists": False,
        "marker_exists": False,
        "python_under_data_dir": True,
        "agent_package_survived": False,
        "interpreter_output": "42",
    }
