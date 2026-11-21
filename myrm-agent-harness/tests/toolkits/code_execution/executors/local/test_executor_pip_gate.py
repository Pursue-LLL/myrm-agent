"""LocalExecutor: a Python snippet or a background command that names pip waits for the shared venv's pip bootstrap.

A bash command takes the same wait inside ``VenvManager.rewrite_pip_command`` (test_venv_pip_bootstrap.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext, ExecutionResult

_PYTHON_RUN = "myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess.run_python_subprocess"
_BACKGROUND_SPAWN = (
    "myrm_agent_harness.toolkits.code_execution.executors.local._background_spawn.spawn_background_process"
)


def _executor(tmp_path: Path) -> LocalExecutor:
    config = ExecutionConfig()
    config.local.shared_venv_path = str(tmp_path / "venvs")
    return LocalExecutor(config)


async def test_a_python_run_waits_for_pip_after_the_interpreter_and_before_running(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    order: list[str] = []
    code = "import subprocess\nsubprocess.run(['pip', 'list'])"

    async def interpreter() -> str:
        order.append("interpreter")
        return "python"

    async def wait(text: str) -> None:
        order.append(f"wait:{text}")

    async def run(**_kwargs: object) -> ExecutionResult:
        order.append("run")
        return ExecutionResult(success=True)

    with (
        patch.object(executor._venv_manager, "get_python_executable", side_effect=interpreter),
        patch.object(executor._venv_manager, "ensure_pip_ready_for", side_effect=wait),
        patch(_PYTHON_RUN, side_effect=run),
    ):
        await executor._run_subprocess(tmp_path / "wrapper.py", 5, context=ExecutionContext(code=code))

    assert order == ["interpreter", f"wait:{code}", "run"]


@pytest.mark.parametrize(
    ("harness_owned", "waited_on"),
    [(False, ["bash -lc pip install requests"]), (True, [])],
)
async def test_a_background_command_waits_for_pip_unless_the_harness_owns_it(
    tmp_path: Path, harness_owned: bool, waited_on: list[str]
) -> None:
    executor = _executor(tmp_path)
    waited: list[str] = []

    async def wait(text: str) -> None:
        waited.append(text)

    context = ExecutionContext(code="bash", args=["-lc", "pip install requests"], harness_owned=harness_owned)
    with (
        patch.object(executor._venv_manager, "ensure_pip_ready_for", side_effect=wait),
        patch(_BACKGROUND_SPAWN, new=AsyncMock()) as spawn,
    ):
        await executor.spawn_background_process(context)

    assert waited == waited_on
    spawn.assert_awaited_once()
