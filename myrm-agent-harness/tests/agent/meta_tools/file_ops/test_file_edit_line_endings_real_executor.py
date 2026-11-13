"""A file the file tools edit keeps its line endings: a CRLF file stays CRLF and an LF file stays LF.

Real chain: ``file_read_tool`` and ``file_edit_tool`` through a ``LocalExecutor`` on real files. The edit pipeline
matches on LF text and writes the file's own endings back, but it can only do that if the read hands it the CRLF: a
read that translated them away made it see an LF file, and the edit turned every CRLF line into LF.
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

_CRLF = b"def a():\r\n    return 1\r\n\r\ndef b():\r\n    return 2\r\n"
_LF = _CRLF.replace(b"\r\n", b"\n")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path)))
    yield tmp_path
    reset_executor(token)


async def _edit_after_reading(path: str, old: str, new: str) -> str:
    """Edit as a model does: read the file whole first, then send replacement text written with ``\\n``."""
    await create_file_read_tool().ainvoke({"paths": [path]}, config=RunnableConfig())
    result = await create_file_edit_tool().ainvoke(
        {"path": path, "edits": [{"old_str": old, "new_str": new}]}, config=RunnableConfig()
    )
    assert isinstance(result, str)
    return result


async def test_an_edit_keeps_every_line_of_a_crlf_file_crlf(workspace: Path) -> None:
    (workspace / "mod.py").write_bytes(_CRLF)

    await _edit_after_reading("mod.py", "return 1", "return 10")

    assert (workspace / "mod.py").read_bytes() == _CRLF.replace(b"return 1", b"return 10")


async def test_a_multi_line_edit_written_with_lf_matches_a_crlf_file_and_keeps_it_crlf(workspace: Path) -> None:
    (workspace / "mod.py").write_bytes(_CRLF)

    await _edit_after_reading("mod.py", "def a():\n    return 1\n", "def a():\n    return 10\n")

    assert (workspace / "mod.py").read_bytes() == _CRLF.replace(b"return 1", b"return 10")


async def test_an_edit_keeps_an_lf_file_lf(workspace: Path) -> None:
    (workspace / "mod.py").write_bytes(_LF)

    await _edit_after_reading("mod.py", "return 1", "return 10")

    assert (workspace / "mod.py").read_bytes() == _LF.replace(b"return 1", b"return 10")


async def test_the_view_of_a_crlf_file_shows_plain_lines(workspace: Path) -> None:
    """The read hands the engine the CRLF, but the model is shown the lines, not the carriage returns."""
    (workspace / "mod.py").write_bytes(_CRLF)
    read = create_file_read_tool()

    whole = await read.ainvoke({"paths": ["mod.py"]}, config=RunnableConfig())
    ranged = await read.ainvoke({"paths": ["mod.py:4-5"]}, config=RunnableConfig())

    assert isinstance(whole, str)
    assert isinstance(ranged, str)
    assert "\r" not in whole + ranged
    assert "2|    return 1\n" in whole
    assert "4|def b():\n" in ranged
    assert "5|    return 2\n" in ranged
