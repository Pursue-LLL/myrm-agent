"""The genuine bash tool on a genuine local executor in a temporary workspace.

Some defects live between layers: the header the persistent shell session injects, how a foreground run differs
from a background spawn, what the path guard sees. A mocked executor cannot show them, so tests of that kind drive
the real stack end to end: ``bash_code_execute_tool`` -> ``BashExecutor`` -> ``LocalExecutor`` -> a real shell or
Python subprocess. There is no OS sandbox, no model and no network. A background job therefore runs on a
pseudo-terminal, as it does in a container; on a Mac with the sandbox on, the production path starts it on pipes.
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
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
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
SESSION_ID = "real-stack"
_BACKGROUND_WAIT_SECONDS = 10


@dataclass(frozen=True)
class BackgroundRun:
    """What a finished background job left: its exit code and what it printed on each stream."""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class StubBin:
    """A directory in front of the PATH the stack's shell inherits, holding stand-ins for host tools."""

    directory: Path

    def add(self, name: str, script: str) -> None:
        """Make *name* a POSIX shell script with the body *script*, run in place of the host's tool."""
        path = self.directory / name
        path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
        path.chmod(0o755)


@dataclass(frozen=True)
class RealBashStack:
    """One chat's bash tool: every call goes through the same persistent shell session."""

    workspace: Path
    tool: BaseTool
    process_tool: BaseTool
    config: RunnableConfig

    async def run(self, command: str, *, timeout: int | None = None) -> str:
        """One foreground call; returns the text the model would read."""
        arguments: dict[str, object] = {"command": command, "reason": _REASON}
        if timeout is not None:
            arguments["timeout"] = timeout
        result = await self.tool.ainvoke(arguments, config=self.config)
        assert isinstance(result, dict)
        return str(result["content"])

    async def start_background(self, command: str) -> int:
        """Start *command* as a background job and return its pid; the caller owns the job and ends it with ``stop_job``."""
        spawned = await self.tool.ainvoke(
            {"command": command, "reason": _REASON, "run_in_background": True}, config=self.config
        )
        assert isinstance(spawned, dict)
        return int(spawned["metadata"]["pid"])

    async def run_detaching(self, command: str, *, yield_after_seconds: int) -> tuple[str, int]:
        """A foreground call of a build or test command that outlives its yield window and becomes a background job.

        Returns the text the model reads and the pid of the job; the caller ends the job with ``stop_job``.
        """
        result = await self.tool.ainvoke(
            {"command": command, "reason": _REASON, "yield_after_seconds": yield_after_seconds}, config=self.config
        )
        assert isinstance(result, dict)
        return str(result["content"]), int(result["metadata"]["pid"])

    async def read_job(self, pid: int) -> dict[str, object]:
        """One ``output`` call on job *pid*: the fields the model reads."""
        polled = await self.process_tool.ainvoke({"action": "output", "pid": pid}, config=self.config)
        assert isinstance(polled, dict)
        content = polled["content"]
        assert isinstance(content, dict)
        return content

    async def send_to_job(self, pid: int, data: str) -> None:
        """Answer job *pid* the way the model does: the text plus Enter."""
        await self.process_tool.ainvoke({"action": "submit_stdin", "pid": pid, "data": data}, config=self.config)

    async def stop_job(self, pid: int) -> None:
        await self.process_tool.ainvoke({"action": "kill", "pid": pid}, config=self.config)

    async def run_background(self, command: str, *, reply: str | None = None) -> BackgroundRun:
        """Start *command* as a background job, wait for it to end and return what it printed.

        Raises ``TimeoutError`` when the job has not ended after ``_BACKGROUND_WAIT_SECONDS``.

        *reply*, when given, goes to the job's stdin through ``bash_process_tool`` right after the start, the way the
        model answers a prompt. The job is killed when the call ends, so one that never ends leaves no child process
        and no slot of the session's background-job limit behind.
        """
        pid = await self.start_background(command)
        try:
            if reply is not None:
                await self.send_to_job(pid, reply)
            await self.process_tool.ainvoke(
                {"action": "wait", "pid": pid, "timeout_seconds": _BACKGROUND_WAIT_SECONDS}, config=self.config
            )
            content = await self.read_job(pid)
            out, err, exit_code = content["stdout"], content["stderr"], content["exit_code"]
            assert isinstance(out, list)
            assert isinstance(err, list)
            stdout = "\n".join(out)
            stderr = "\n".join(err)
            if exit_code is None:
                raise TimeoutError(
                    f"background job {command!r} had not ended after {_BACKGROUND_WAIT_SECONDS}s; "
                    f"stdout={stdout!r} stderr={stderr!r}"
                )
            assert isinstance(exit_code, int)
            return BackgroundRun(exit_code=exit_code, stdout=stdout, stderr=stderr)
        finally:
            await self.stop_job(pid)


@asynccontextmanager
async def real_bash_stack(workspace: Path, *, storage_root: Path | None = None) -> AsyncIterator[RealBashStack]:
    """Build the stack on *workspace* and release its shell sessions and bindings on exit.

    *workspace* is the directory the executor is bound to, the one ``/workspace`` means to a command.
    *storage_root* is where the host keeps each chat's own workspace directory; it defaults to *workspace*, which is
    the shape of a chat bound to a project: the project is in use and the chat's own directory lies elsewhere.
    """
    no_sandbox = (NullProvider(), SandboxStatus(enabled=False, provider_name="null", reason="test"))
    storage = storage_root or workspace
    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(workspace))
    executor_token = set_executor(executor)
    storage_token = bind_workspace_storage_root(storage)
    config: RunnableConfig = {
        "configurable": {
            "context": {
                "session_id": SESSION_ID,
                "workspace_path": str(workspace),
                "workspaces_storage_root": str(storage),
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
            yield RealBashStack(
                workspace=workspace,
                tool=create_bash_code_execute_tool(),
                process_tool=create_bash_process_tool(),
                config=config,
            )
        finally:
            await executor.close()
            release_workspace_storage_bind_token(storage_token)
            reset_executor(executor_token)
