"""A failed edit tells the model the way out that fits the failure, through the real engine and tool.

Real chain: ``file_read_tool`` and ``file_edit_tool`` through a ``LocalExecutor`` on real files, and the text the model
reads is the tool error as the agent formats it. A test that hands the tool a made-up error message cannot see the
engine's wording drift away from the tool's mapping, which is how the multiple-match hint became unreachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_edit_tool import create_file_edit_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.errors import ToolError


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path)))
    yield tmp_path
    reset_executor(token)


async def _what_the_model_reads_after_a_failed_edit(path: str, edits: list[dict[str, str]]) -> str:
    """Read the file as a model does, send the edits, and return the error text the failed edit gives the model."""
    await create_file_read_tool().ainvoke({"paths": [path]}, config=RunnableConfig())
    with pytest.raises(ToolError) as failure:
        await create_file_edit_tool().ainvoke({"path": path, "edits": edits}, config=RunnableConfig())
    return failure.value.format_for_llm()


async def test_a_text_that_occurs_twice_gets_the_multiple_matches_hint(workspace: Path) -> None:
    (workspace / "a.txt").write_text("x = 1\nx = 1\n")

    text = await _what_the_model_reads_after_a_failed_edit("a.txt", [{"old_str": "x = 1", "new_str": "x = 2"}])

    assert "Found 2 matches" in text
    assert "Hint: An old_str matches multiple times. Add surrounding context to make it unique." in text


async def test_a_text_that_is_not_in_the_file_gets_the_not_found_hint(workspace: Path) -> None:
    (workspace / "a.txt").write_text("x = 1\n")

    text = await _what_the_model_reads_after_a_failed_edit("a.txt", [{"old_str": "y = 2", "new_str": "y = 3"}])

    assert "text not found in file" in text
    assert "Hint: An old_str was not found." in text


async def test_overlapping_edits_get_the_overlap_hint(workspace: Path) -> None:
    (workspace / "a.txt").write_text("alpha beta gamma\n")

    text = await _what_the_model_reads_after_a_failed_edit(
        "a.txt",
        [{"old_str": "alpha beta", "new_str": "A"}, {"old_str": "beta gamma", "new_str": "B"}],
    )

    assert "overlap in the original file" in text
    assert "Hint: Edits overlap in the file." in text


async def test_a_failure_that_is_not_about_matching_keeps_the_general_hint(workspace: Path) -> None:
    (workspace / "a.txt").write_text("x = 1\n")

    text = await _what_the_model_reads_after_a_failed_edit("a.txt", [{"old_str": "", "new_str": "y"}])

    assert "Hint: Invalid edit parameters. Check path and edits array." in text
