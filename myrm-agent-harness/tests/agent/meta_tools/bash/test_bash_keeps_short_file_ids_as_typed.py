"""A bash command runs as the text the permission engine judged: a short file id in it is not swapped for a path.

The run's id registry numbers files from ``@file_001`` afresh on every run, so a swap would run the command on a file the
verdict never saw (or, after a resume, on another file than the one the model meant).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.artifacts import ArtifactContextManager, register_file
from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionResult

REGISTERED_PATH = "/ws/reports/q3.txt"


@pytest.fixture(autouse=True)
def registered_id() -> Iterator[str]:
    """The run has registered a file, so ``@file_001`` names it for the UI."""
    with ArtifactContextManager():
        file_id = register_file(REGISTERED_PATH)
        assert file_id == "@file_001"
        yield file_id


@asynccontextmanager
async def _bash() -> AsyncIterator[tuple[BashExecutor, MagicMock]]:
    code_executor = MagicMock()
    code_executor.config.network.allow_network = True
    code_executor.config.network.get_effective_allowed_hosts.return_value = []
    code_executor.config.local.max_execution_time = 120
    code_executor.get_executor_name.return_value = "mock"
    code_executor.execute_bash = AsyncMock(
        return_value=ExecutionResult(success=True, result=0, stdout="ok", stderr="", container_id="c")
    )
    code_executor.spawn_background_process = AsyncMock(return_value=MagicMock())
    bash = BashExecutor(code_executor, enable_skill_execution=False)
    with (
        patch.object(bash._workspace_manager, "get_or_create", AsyncMock(return_value=(MagicMock(), None))),
        patch.object(bash._workspace_manager, "get_workspace_path", return_value="/ws"),
        patch.object(bash._workspace_manager, "update_workspace_timestamp", AsyncMock()),
        patch.object(bash, "_log_bash_command_execution", AsyncMock()),
        patch("myrm_agent_harness.agent.meta_tools.bash._background.registry.get_background_registry") as registry,
    ):
        registry.return_value.register = AsyncMock(return_value=MagicMock(pid=1, command="tail", status="running"))
        yield bash, code_executor


async def test_a_command_runs_with_the_id_as_typed(registered_id: str) -> None:
    async with _bash() as (bash, code_executor):
        await bash.execute(f"cat {registered_id}", session_id="s")

    code = code_executor.execute_bash.call_args.args[0].code
    assert registered_id in code
    assert REGISTERED_PATH not in code


async def test_a_background_command_is_spawned_with_the_id_as_typed(registered_id: str) -> None:
    async with _bash() as (bash, code_executor):
        await bash.spawn_background(f"tail -f {registered_id}", session_id="s")

    spawned = code_executor.spawn_background_process.await_args.args[0].args[1]
    assert spawned.endswith(f"tail -f {registered_id}")
    assert REGISTERED_PATH not in spawned
