"""A file-tool call that carries ``verify_command`` is served, and the command it names never runs.

No file tool takes a command, so the argument is ignored like any other undeclared one; a command put in an argument
must not run under the file tool's permission verdict, which never reads the arguments.

Real chain: the file tools through a ``LocalExecutor`` on real files.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_edit_tool import create_file_edit_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path)))
    yield tmp_path
    reset_executor(token)


async def test_an_edit_that_carries_verify_command_is_applied_and_the_command_never_runs(workspace: Path) -> None:
    marker = workspace / "ran.marker"
    (workspace / "mod.txt").write_text("alpha\n", encoding="utf-8")
    await create_file_read_tool().ainvoke({"paths": ["mod.txt"]}, config=RunnableConfig())

    result = await create_file_edit_tool().ainvoke(
        {
            "path": "mod.txt",
            "edits": [{"old_str": "alpha", "new_str": "beta"}],
            "verify_command": f"touch {marker}",
        },
        config=RunnableConfig(),
    )

    assert isinstance(result, str)
    assert (workspace / "mod.txt").read_text(encoding="utf-8") == "beta\n"
    assert not marker.exists()


async def test_a_write_that_carries_verify_command_is_applied_and_the_command_never_runs(workspace: Path) -> None:
    marker = workspace / "ran.marker"

    result = await create_file_write_tool().ainvoke(
        {"path": "new.txt", "content": "beta\n", "verify_command": f"touch {marker}"},
        config=RunnableConfig(),
    )

    assert isinstance(result, str)
    assert (workspace / "new.txt").read_text(encoding="utf-8") == "beta\n"
    assert not marker.exists()
