"""A file the file tools edit keeps its line endings: a CRLF file stays CRLF and an LF file stays LF.

Real chain: ``file_read_tool`` and ``file_edit_tool`` through a ``LocalExecutor`` on real files. The edit pipeline
matches on LF text and writes the file's own endings back, but it can only do that if the read hands it the CRLF: a
read that translated them away made it see an LF file, and the edit turned every CRLF line into LF.

The view is the other side of that: whatever ends a line (CRLF, a bare CR or LF), the model is shown the lines of the
text and can read a range of them.
"""

from __future__ import annotations

import re
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

# Two blank lines between the functions: the edit runs ``ruff format`` on a Python file when ruff is on PATH, and this is
# the form it leaves as it is, so the bytes asserted below are the same with or without a formatter installed.
_CRLF = b"def a():\r\n    return 1\r\n\r\n\r\ndef b():\r\n    return 2\r\n"
_LF = _CRLF.replace(b"\r\n", b"\n")
_CR_ONLY = b"a1\rb2\rc3\r"


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
    ranged = await read.ainvoke({"paths": ["mod.py:5-6"]}, config=RunnableConfig())

    assert isinstance(whole, str)
    assert isinstance(ranged, str)
    assert "\r" not in whole + ranged
    assert "2|    return 1\n" in whole
    assert "5|def b():\n" in ranged
    assert "6|    return 2\n" in ranged


async def _read(path: str) -> str:
    result = await create_file_read_tool().ainvoke({"paths": [path]}, config=RunnableConfig())
    assert isinstance(result, str)
    return result


def _numbered_lines(read_result: str) -> list[str]:
    """What the model is shown of a file: the numbered lines, without the wrapper (whose id differs on every read)."""
    return [line for line in read_result.split("\n") if re.match(r" *\d+\|", line)]


async def test_the_view_of_a_cr_only_file_shows_the_lines_of_the_same_text_with_lf(workspace: Path) -> None:
    """A file with a bare ``\\r`` after every line is not one long line: it shows the lines an LF file shows."""
    (workspace / "old_mac.txt").write_bytes(_CR_ONLY)
    (workspace / "unix.txt").write_bytes(_CR_ONLY.replace(b"\r", b"\n"))

    cr_only = await _read("old_mac.txt")
    lf = await _read("unix.txt")

    assert _numbered_lines(cr_only) == _numbered_lines(lf)
    assert "2|b2\n" in cr_only
    assert "(4 lines)" in cr_only
    assert "\r" not in cr_only


async def test_a_line_range_of_a_cr_only_file_finds_the_line(workspace: Path) -> None:
    (workspace / "old_mac.txt").write_bytes(_CR_ONLY)

    ranged = await _read("old_mac.txt:2-2")

    assert "(lines 2-2 of 4)" in ranged
    assert "2|b2\n" in ranged
    assert "1|a1" not in ranged


async def test_an_edit_of_a_cr_only_file_keeps_its_carriage_returns(workspace: Path) -> None:
    """The view shows lines, but the edit and the integrity check work on the bytes of the file."""
    (workspace / "old_mac.txt").write_bytes(_CR_ONLY)

    await _edit_after_reading("old_mac.txt", "b2", "B2")

    assert (workspace / "old_mac.txt").read_bytes() == _CR_ONLY.replace(b"b2", b"B2")
