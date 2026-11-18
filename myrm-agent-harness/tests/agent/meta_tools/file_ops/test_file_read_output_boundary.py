"""file_read puts default-mode text, line-range text and directory listings inside a TOOL_OUTPUT envelope.

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

_OPEN = '<<<TOOL_OUTPUT id="'
_CLOSE = '<<<END_TOOL_OUTPUT id="'


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    (root / "notes.txt").write_text("alpha line\nbeta line\n", encoding="utf-8")
    (root / "pkg").mkdir()
    (root / "pkg" / "inner.txt").write_text("x\n", encoding="utf-8")
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    root_token = workspace_root_var.set(str(root))
    try:
        yield root
    finally:
        workspace_root_var.reset(root_token)
        reset_executor(executor_token)


def _assert_inside_envelope(out: object, text: str) -> None:
    assert isinstance(out, str)
    assert out.count(_OPEN) == 1
    assert out.count(_CLOSE) == 1
    assert out.index(_OPEN) < out.index(text) < out.index(_CLOSE)


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "text"), [("notes.txt", "alpha line"), ("notes.txt:2-2", "beta line")])
async def test_text_reads_are_wrapped_as_tool_output(workspace: Path, path: str, text: str) -> None:
    out = await create_file_read_tool().ainvoke({"paths": [path]}, config=RunnableConfig())

    _assert_inside_envelope(out, text)


@pytest.mark.asyncio
async def test_directory_listing_is_wrapped_as_tool_output(workspace: Path) -> None:
    out = await create_file_read_tool().ainvoke({"paths": ["pkg"]}, config=RunnableConfig())

    _assert_inside_envelope(out, "inner.txt")
