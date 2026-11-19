"""``file_read_tool`` with a colon in the path: only a trailing ``:START-END`` is a line range.

``C:`` below is a directory under the workspace, the POSIX stand-in for a Windows drive letter. The tool classifies,
guards and words a path from its file path, so that file path must be the one the reader opens: a Word document is
parsed as a document, a continuation hint names a file that exists, the disabled-skill block judges the real path,
and ``preview`` and ``stream`` open a big file whatever colons its path holds. These tests send real reads through
``file_read_tool`` with a real ``LocalExecutor``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.constants import MAX_FILE_READ_SIZE_BYTES
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.utils.errors import ToolError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="A directory named C: cannot exist on Windows")


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve() / "ws"
    (root / "C:" / "docs").mkdir(parents=True)
    (root / "C:" / "skills" / "off").mkdir(parents=True)
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    workspace_token = workspace_root_var.set(str(root))
    yield root
    workspace_root_var.reset(workspace_token)
    reset_executor(executor_token)


async def _read(path: str, *, mode: str = "all", config: RunnableConfig | None = None) -> str:
    tool = create_file_read_tool()
    return str(await tool.ainvoke({"paths": [path], "mode": mode}, config=config or RunnableConfig()))


@pytest.mark.asyncio
async def test_a_word_document_under_a_drive_style_path_is_parsed_as_a_document(workspace: Path) -> None:
    docx = pytest.importorskip("docx", reason="python-docx not installed")
    document = docx.Document()
    document.add_paragraph("QUARTERLY-PLAN-TEXT")
    document.save(str(workspace / "C:" / "docs" / "plan.docx"))

    text = await _read("C:/docs/plan.docx")

    assert "[Document: C:/docs/plan.docx]" in text
    assert "QUARTERLY-PLAN-TEXT" in text


@pytest.mark.asyncio
async def test_the_continuation_hint_of_a_file_with_a_colon_in_its_name_reads_on(workspace: Path) -> None:
    lines = [f"line-{number:04d}" for number in range(2000)]
    (workspace / "notes:v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    first = await _read("notes:v2.md")

    hint = re.search(r"Use notes:v2\.md:(\d+)- to continue", first)
    assert hint is not None, first
    next_line = int(hint.group(1))
    resumed = await _read(f"notes:v2.md:{next_line}-")
    assert f"{next_line}|line-{next_line - 1:04d}" in resumed


@pytest.mark.asyncio
async def test_a_disabled_skill_under_a_drive_style_path_is_blocked(workspace: Path) -> None:
    skill_root = workspace / "C:" / "skills" / "off"
    (skill_root / "SECRET.md").write_text("DISABLED-SKILL-SECRET\n", encoding="utf-8")
    config = RunnableConfig(configurable={"context": {"disabled_skill_roots": [str(skill_root)]}})

    with pytest.raises(ToolError, match="Path blocked"):
        await _read("C:/skills/off/SECRET.md", config=config)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "header"),
    [("preview", "=== C:/huge.log (preview mode) ==="), ("stream", "=== C:/huge.log ===")],
)
async def test_preview_and_stream_open_a_big_file_under_a_drive_style_path(
    workspace: Path, mode: str, header: str
) -> None:
    line = "x" * 99 + "\n"
    (workspace / "C:" / "huge.log").write_text(line * (MAX_FILE_READ_SIZE_BYTES // len(line) + 1), encoding="utf-8")

    text = await _read("C:/huge.log", mode=mode)

    assert text.startswith(header)
