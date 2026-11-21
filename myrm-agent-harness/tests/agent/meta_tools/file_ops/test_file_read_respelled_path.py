"""``file_read_tool`` opens the on-disk spelling of a path the model typed with quotes or compatibility characters.

The permission engine judges the typed spelling and the opened one (``test_engine_respelled_paths.py``), so the tool
heals without a verdict of its own. The one respelling it refuses is a credential file the typed text does not name:
the credential labelling of a read reads the typed text.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.errors import ToolError

CANARY = "ocean-blue-7"


@pytest.fixture
def run_in_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".env").write_text(CANARY)
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(workspace)))
    root_token = workspace_root_var.set(str(workspace))
    yield workspace
    workspace_root_var.reset(root_token)
    reset_executor(executor_token)


async def _read(path: str) -> str:
    try:
        return str(await create_file_read_tool().ainvoke({"paths": [path]}, config=RunnableConfig()))
    except ToolError as failure:
        return failure.format_for_llm()


async def test_the_read_tool_opens_a_respelled_ordinary_path(run_in_workspace: Path) -> None:
    (run_in_workspace / "It's plan.md").write_text("plan body")

    assert "plan body" in await _read("It\u2019s plan.md")


async def test_the_read_tool_keeps_the_line_range_of_a_respelled_path(run_in_workspace: Path) -> None:
    (run_in_workspace / "plan.md").write_text("first line\nsecond line\nthird line\n")

    content = await _read("\u201cplan.md\u201d:1-2")

    assert "first line" in content
    assert "second line" in content
    assert "third line" not in content


async def test_the_read_tool_does_not_open_a_credential_file_through_a_respelled_path(run_in_workspace: Path) -> None:
    assert CANARY not in await _read('".env"')
