"""A bash command that names a relative Office file still runs when the session has no workspace; the audit needs one."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionResult


async def test_relative_office_path_without_workspace_still_runs() -> None:
    code_executor = MagicMock()
    code_executor.config.network.allow_network = True
    code_executor.config.network.get_effective_allowed_hosts.return_value = []
    code_executor.config.local.max_execution_time = 120
    code_executor.get_executor_name.return_value = "mock"
    code_executor.execute_bash = AsyncMock(
        return_value=ExecutionResult(success=True, result=0, stdout="ok", stderr="", container_id="c")
    )
    bash = BashExecutor(code_executor, enable_skill_execution=False)

    with (
        patch.object(bash._workspace_manager, "get_or_create", AsyncMock(return_value=(None, None))),
        patch.object(bash._workspace_manager, "update_workspace_timestamp", AsyncMock()),
        patch.object(bash, "_log_bash_command_execution", AsyncMock()),
    ):
        result = await bash.execute("cat report.docx", session_id="s")

    assert result["stdout"] == "ok"
    assert result["office_warnings"] == []
    code_executor.execute_bash.assert_awaited_once()
