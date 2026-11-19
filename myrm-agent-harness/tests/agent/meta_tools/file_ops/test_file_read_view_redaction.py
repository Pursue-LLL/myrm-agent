"""file_read redacts each path by its own file type: source files in source mode, every other file in full.

Runs the real chain: ``file_read_tool`` through a ``LocalExecutor`` on real files.
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

_CODE = "total_api_tokens = 0\npassword: str\n"
_LITERAL = 'DEFAULT_PASSWORD = "Xk9$mP2vLq8"\n'
_ASSIGNMENTS = "total_api_tokens = 0\nDB_PASSWORD=hunter2\n"


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    (root / "a.py").write_text(_CODE + _LITERAL, encoding="utf-8")
    (root / "app.conf").write_text(_ASSIGNMENTS, encoding="utf-8")
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    root_token = workspace_root_var.set(str(root))
    try:
        yield root
    finally:
        workspace_root_var.reset(root_token)
        reset_executor(executor_token)


@pytest.mark.asyncio
async def test_the_tool_redacts_each_path_by_its_own_type(workspace: Path) -> None:
    out = await create_file_read_tool().ainvoke({"paths": ["a.py", "app.conf"]}, config=RunnableConfig())

    assert isinstance(out, str)
    assert "total_api_tokens = 0" in out
    assert "password: str" in out
    assert "Xk9$mP2vLq8" not in out
    assert "hunter2" not in out
    assert "total_api_tokens=***" in out
