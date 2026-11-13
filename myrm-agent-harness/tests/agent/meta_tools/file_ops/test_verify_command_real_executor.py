"""A verify command runs from the workspace root; only a command that ran and failed undoes the write.

Real chain: ``file_write_tool`` / ``file_edit_tool`` through a ``LocalExecutor`` that runs the commands in a real shell.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_edit_tool import create_file_edit_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.errors import ToolError

# The command safety check refuses inline Python, so this command never reaches a shell.
_BLOCKED_COMMAND = "python -c 'print(1)'"
# Exits 1 in a real shell: the file it names is not there.
_FAILING_COMMAND = "test -f missing.txt"


@pytest.fixture
def executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LocalExecutor]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
    token = set_executor(local)
    yield local
    reset_executor(token)


@pytest.fixture(autouse=True)
async def _close_shells(executor: LocalExecutor) -> AsyncIterator[None]:
    yield
    await executor.close()


@pytest.fixture
def workspace(tmp_path: Path, executor: LocalExecutor) -> Path:
    return tmp_path


async def _write(path: str, content: str, verify_command: str | None = None) -> str:
    result = await create_file_write_tool().ainvoke(
        {"path": path, "content": content, "verify_command": verify_command}, config=RunnableConfig()
    )
    assert isinstance(result, str)
    return result


async def _edit(path: str, old: str, new: str, verify_command: str | None = None) -> str:
    result = await create_file_edit_tool().ainvoke(
        {"path": path, "edits": [{"old_str": old, "new_str": new}], "verify_command": verify_command},
        config=RunnableConfig(),
    )
    assert isinstance(result, str)
    return result


async def test_a_relative_path_in_the_command_means_the_workspace_root(workspace: Path) -> None:
    result = await _write("pkg/mod.py", "x = 1\n", verify_command="test -f pkg/mod.py")

    assert "Successfully created" in result
    assert "did not run" not in result
    assert (workspace / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


async def test_a_command_that_ran_and_failed_deletes_the_new_file(workspace: Path) -> None:
    with pytest.raises(ToolError, match="verification failed"):
        await _write("pkg/mod.py", "x = 1\n", verify_command=_FAILING_COMMAND)

    assert not (workspace / "pkg" / "mod.py").exists()


async def test_a_blocked_command_keeps_the_new_file_and_says_nothing_was_checked(workspace: Path) -> None:
    result = await _write("pkg/mod.py", "x = 1\n", verify_command=_BLOCKED_COMMAND)

    assert "Successfully created" in result
    assert "Verify command did not run: Command blocked for security reasons" in result
    assert (workspace / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


async def test_a_command_that_ran_and_failed_rolls_the_edit_back(workspace: Path) -> None:
    await _write("mod.py", "x = 1\n")

    with pytest.raises(ToolError, match="verification failed"):
        await _edit("mod.py", "x = 1", "x = 2", verify_command=_FAILING_COMMAND)

    assert (workspace / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


async def test_a_blocked_command_keeps_the_edit_and_says_nothing_was_checked(workspace: Path) -> None:
    await _write("mod.py", "x = 1\n")

    result = await _edit("mod.py", "x = 1", "x = 2", verify_command=_BLOCKED_COMMAND)

    assert "Verify command did not run: Command blocked for security reasons" in result
    assert (workspace / "mod.py").read_text(encoding="utf-8") == "x = 2\n"
