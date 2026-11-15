"""The genuine bash tool on a genuine local executor in a temporary workspace.

Some defects live between layers: the header the persistent shell session injects, how a foreground run differs
from a background spawn, what the path guard sees. A mocked executor cannot show them, so tests of that kind drive
the real stack end to end: ``bash_code_execute_tool`` -> ``BashExecutor`` -> ``LocalExecutor`` -> a real shell or
Python subprocess. There is no OS sandbox, no model and no network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
    bind_workspace_storage_root,
    release_workspace_storage_bind_token,
)

_REASON = "exercise the bash tool through the production path"
_SESSION = "real-stack"


@dataclass(frozen=True)
class RealBashStack:
    """One chat's bash tool: every call goes through the same persistent shell session."""

    workspace: Path
    tool: BaseTool
    config: RunnableConfig

    async def run(self, command: str, *, timeout: int | None = None) -> str:
        """One foreground call; returns the text the model would read."""
        arguments: dict[str, object] = {"command": command, "reason": _REASON}
        if timeout is not None:
            arguments["timeout"] = timeout
        result = await self.tool.ainvoke(arguments, config=self.config)
        assert isinstance(result, dict)
        return str(result["content"])


@asynccontextmanager
async def real_bash_stack(workspace: Path) -> AsyncIterator[RealBashStack]:
    """Build the stack on *workspace* and release its shell sessions and bindings on exit."""
    no_sandbox = (NullProvider(), SandboxStatus(enabled=False, provider_name="null", reason="test"))
    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(workspace))
    executor_token = set_executor(executor)
    storage_token = bind_workspace_storage_root(workspace)
    config: RunnableConfig = {
        "configurable": {
            "context": {
                "session_id": _SESSION,
                "workspace_path": str(workspace),
                "workspaces_storage_root": str(workspace),
            }
        }
    }
    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
            return_value=no_sandbox,
        ),
        patch("myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider", return_value=no_sandbox),
        patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()),
    ):
        try:
            yield RealBashStack(workspace=workspace, tool=create_bash_code_execute_tool(), config=config)
        finally:
            await executor.close()
            release_workspace_storage_bind_token(storage_token)
            reset_executor(executor_token)
