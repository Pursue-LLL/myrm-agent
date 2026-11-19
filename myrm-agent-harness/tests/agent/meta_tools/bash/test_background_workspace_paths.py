"""A background command reads ``/workspace`` as a foreground command does: the directory the executor is bound to.

The shell is given the command with that directory in place of ``/workspace``, quoted where a space or a shell
metacharacter in its name needs it. The job list, the execution record and the threat check keep the command as typed.
"""

from __future__ import annotations

from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.toolkits.code_execution.executors.base import ExecutionContext


class _Spawned(NamedTuple):
    """What a spawn left behind: the context the executor got and the two places the command is recorded."""

    context: ExecutionContext
    register: AsyncMock
    record: AsyncMock


async def _spawned(command: str, *, executor_root: str | None, session_root: str) -> _Spawned:
    """Spawn *command* on a mock executor bound to *executor_root*."""
    executor = MagicMock()
    executor.config.network.allow_network = True
    executor.config.network.get_effective_allowed_hosts.return_value = []
    executor.config.local.max_execution_time = 120
    executor.get_executor_name.return_value = "mock"
    executor.workspace_path = executor_root
    executor.spawn_background_process = AsyncMock(return_value=MagicMock())
    bash_exec = BashExecutor(executor, enable_skill_execution=False)
    record = AsyncMock()
    with (
        patch.object(bash_exec._workspace_manager, "get_or_create", AsyncMock(return_value=(MagicMock(), None))),
        patch.object(bash_exec._workspace_manager, "get_workspace_path", return_value=session_root),
        patch.object(bash_exec, "_log_bash_command_execution", record),
        patch("myrm_agent_harness.agent.meta_tools.bash._background.registry.get_background_registry") as registry,
    ):
        registry.return_value.register = AsyncMock(return_value=MagicMock(pid=1))
        await bash_exec.spawn_background(command, session_id="sess-1")
    context = executor.spawn_background_process.await_args.args[0]
    assert isinstance(context, ExecutionContext)
    return _Spawned(context, registry.return_value.register, record)


@pytest.mark.asyncio
async def test_the_container_root_names_the_directory_the_executor_is_bound_to() -> None:
    spawned = await _spawned(
        "cd /workspace/app && ls /workspace", executor_root="/srv/project", session_root="/chats/c1"
    )

    assert spawned.context.args == ["-c", "cd /srv/project/app && ls /srv/project"]


@pytest.mark.asyncio
async def test_a_directory_the_shell_would_split_is_quoted() -> None:
    spawned = await _spawned("cd /workspace/app && ls", executor_root="/srv/My Docs", session_root="/chats/c1")

    assert spawned.context.args == ["-c", "cd '/srv/My Docs'/app && ls"]


@pytest.mark.asyncio
async def test_a_chat_bound_to_no_directory_uses_its_own_workspace() -> None:
    spawned = await _spawned("ls /workspace", executor_root=None, session_root="/chats/c1")

    assert spawned.context.args == ["-c", "ls /chats/c1"]


@pytest.mark.asyncio
async def test_the_job_is_recorded_and_judged_under_the_command_as_typed() -> None:
    spawned = await _spawned("cd /workspace && ls", executor_root="/srv/project", session_root="/chats/c1")

    assert spawned.context.original_code == "cd /workspace && ls"
    assert spawned.register.await_args is not None
    assert spawned.register.await_args.kwargs["command"] == "cd /workspace && ls"
    assert spawned.record.await_args is not None
    assert spawned.record.await_args.kwargs["command"] == "cd /workspace && ls"


@pytest.mark.asyncio
async def test_a_directory_that_is_only_called_workspace_stays_as_typed() -> None:
    typed = "ls ~/workspace ./workspace /home/me/workspace"

    spawned = await _spawned(typed, executor_root="/srv/project", session_root="/chats/c1")

    assert spawned.context.args == ["-c", typed]


@pytest.mark.asyncio
async def test_without_any_root_the_command_goes_as_typed() -> None:
    spawned = await _spawned("ls /workspace", executor_root=None, session_root="")

    assert spawned.context.args == ["-c", "ls /workspace"]
