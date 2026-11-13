"""Reading a file again gives its content again.

The result of an earlier read may have been pruned from what the model sees, so a repeated read never answers with a
pointer back to it. Runs the real chain: ``file_read_tool`` through a ``LocalExecutor`` on a real file.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
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


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["notes.txt", "notes.txt:1-2"])
async def test_every_read_of_an_unchanged_file_returns_its_content(workspace: Path, target: str) -> None:
    (workspace / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    tool = create_file_read_tool()

    for _ in range(3):
        result = await tool.ainvoke({"paths": [target], "mode": "all"}, config=RunnableConfig())

        assert "1|alpha" in result
        assert "2|beta" in result
