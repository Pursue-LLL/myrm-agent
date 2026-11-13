"""file_write_tool only creates: a path that already exists is refused, left untouched, and the refusal names the edit tool.

Runs the real chain: ``file_write_tool`` through a ``LocalExecutor`` on real files.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.errors import ToolError

_SETTINGS = "host: db.internal\napi_key: sk-proj-abcdefghijklmnopqrstuvwxyz1234567890\nport: 5432\n"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path)))
    yield tmp_path
    reset_executor(token)


async def _write(path: str, content: str) -> str:
    result = await create_file_write_tool().ainvoke({"path": path, "content": content}, config=RunnableConfig())
    assert isinstance(result, str)
    return result


@pytest.mark.asyncio
async def test_a_new_path_is_created(workspace: Path) -> None:
    await _write("notes.txt", "alpha\n")

    assert (workspace / "notes.txt").read_text(encoding="utf-8") == "alpha\n"


@pytest.mark.asyncio
async def test_an_existing_path_is_refused_untouched_and_the_hint_names_the_edit_tool(workspace: Path) -> None:
    (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ToolError) as refused:
        await _write("notes.txt", "beta\n")

    assert "already exists" in str(refused.value)
    assert "file_edit_tool" in (refused.value.user_hint or "")
    assert (workspace / "notes.txt").read_text(encoding="utf-8") == "alpha\n"


@pytest.mark.asyncio
async def test_the_masked_view_of_a_file_cannot_be_written_back_over_the_real_values(workspace: Path) -> None:
    (workspace / "settings.yaml").write_text(_SETTINGS, encoding="utf-8")

    with pytest.raises(ToolError):
        await _write("settings.yaml", redact_sensitive_text(_SETTINGS))

    assert (workspace / "settings.yaml").read_text(encoding="utf-8") == _SETTINGS
