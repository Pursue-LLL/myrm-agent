"""The shell that reads a background command follows the platform, not the name ``sh``, and only bash reads the header."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.background_mixin import _background_shell
from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.platform import ShellType, detect_platform

_MIXIN = "myrm_agent_harness.agent.meta_tools.bash._executor.background_mixin"
_DETECT_PLATFORM = f"{_MIXIN}.detect_platform"
_REGISTRY = "myrm_agent_harness.agent.meta_tools.bash._background.registry.get_background_registry"


def test_a_host_with_bash_reads_a_job_with_the_path_of_its_bash() -> None:
    host = replace(detect_platform(), shell_type="bash", shell_path="/opt/bash/bin/bash")

    with patch(_DETECT_PLATFORM, return_value=host):
        assert _background_shell() == "/opt/bash/bin/bash"


@pytest.mark.parametrize("shell_type", ["powershell", "cmd"])
def test_a_host_without_bash_reads_a_job_with_the_sh_on_its_path(shell_type: ShellType) -> None:
    host = replace(detect_platform(), shell_type=shell_type, shell_path="C:/shell/host.exe")

    with patch(_DETECT_PLATFORM, return_value=host):
        assert _background_shell() == "sh"


async def _spawned_context(command: str, shell: str) -> ExecutionContext:
    """The context the executor is asked to spawn a job of *command* with, on a host whose job shell is *shell*."""
    code_executor = MagicMock()
    code_executor.config.network.allow_network = True
    code_executor.config.network.get_effective_allowed_hosts.return_value = []
    code_executor.spawn_background_process = AsyncMock(return_value=MagicMock())
    bash = BashExecutor(code_executor, enable_skill_execution=False)
    with (
        patch(f"{_MIXIN}._background_shell", return_value=shell),
        patch.object(bash._workspace_manager, "get_or_create", AsyncMock(return_value=(MagicMock(), None))),
        patch.object(bash._workspace_manager, "get_workspace_path", return_value="/ws"),
        patch.object(bash, "_log_bash_command_execution", AsyncMock()),
        patch(_REGISTRY) as registry,
    ):
        registry.return_value.register = AsyncMock(return_value=MagicMock(pid=1))
        await bash.spawn_background(command, session_id="s")

    spawn = code_executor.spawn_background_process
    assert spawn.await_args is not None
    context: ExecutionContext = spawn.await_args.args[0]
    return context


async def test_a_job_of_a_bash_host_reads_the_header_before_its_command() -> None:
    context = await _spawned_context("sleep 1", "/opt/bash/bin/bash")

    assert context.code == "/opt/bash/bin/bash"
    assert context.args is not None
    assert context.args[0] == "-c"
    assert "Resilience Init Script" in context.args[1]
    assert context.args[1].endswith("\n\nsleep 1")
    assert context.original_code == "sleep 1"


async def test_a_job_of_a_host_without_bash_reads_its_command_alone() -> None:
    """The header is bash text: the ``sh`` that stands in could be dash, which cannot read it."""
    context = await _spawned_context("sleep 1", "sh")

    assert context.args == ["-c", "sleep 1"]
