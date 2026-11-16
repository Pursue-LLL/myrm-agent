"""A line-range read counts as a read of the file: the edit that follows it is not refused for being partial.

The read gate asks that the model has read the file; the version gate compares the hash of the whole file recorded at
that read with the file on disk. A range read holds the whole file in memory like any read, so it records the same
hash, and an edit right after it needs no second, full read. ``old_str`` still has to match exactly one place.

Real file tools and a real local executor; preview and stream reads open the file themselves and record nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
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

_LINES = [f"line {n}" for n in range(1, 301)]


@pytest.fixture
def executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LocalExecutor]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
    token = set_executor(local)
    yield local
    reset_executor(token)


@pytest.fixture(autouse=True)
async def _close_shells(executor: LocalExecutor) -> AsyncIterator[None]:
    yield
    await executor.close()


@pytest.fixture
def big_file(tmp_path: Path, executor: LocalExecutor) -> Path:
    path = tmp_path / "big.txt"
    path.write_text("\n".join(_LINES) + "\n", encoding="utf-8")
    return path


async def _read(path: str, mode: str = "all") -> None:
    await create_file_read_tool().ainvoke({"paths": [path], "mode": mode}, config=RunnableConfig())


async def _edit(path: str, old: str, new: str) -> str:
    result = await create_file_edit_tool().ainvoke(
        {"path": path, "edits": [{"old_str": old, "new_str": new}]}, config=RunnableConfig()
    )
    assert isinstance(result, str)
    return result


class TestAfterALineRangeRead:
    async def test_an_edit_inside_the_range_succeeds(self, big_file: Path) -> None:
        await _read("big.txt:100-110")

        result = await _edit("big.txt", "line 105\n", "LINE 105\n")

        assert "Successfully" in result
        assert "LINE 105" in big_file.read_text(encoding="utf-8")

    async def test_an_edit_of_a_line_the_range_never_showed_succeeds(self, big_file: Path) -> None:
        await _read("big.txt:100-110")

        await _edit("big.txt", "line 250\n", "LINE 250\n")

        assert "LINE 250" in big_file.read_text(encoding="utf-8")

    async def test_an_old_str_that_hits_several_places_is_still_refused(self, big_file: Path) -> None:
        await _read("big.txt:100-110")

        with pytest.raises(ToolError, match=r"(?i)found \d+ matches"):
            await _edit("big.txt", "line 1", "LINE 1")

        assert big_file.read_text(encoding="utf-8") == "\n".join(_LINES) + "\n"

    async def test_a_change_to_the_target_on_disk_since_the_read_is_still_refused(self, big_file: Path) -> None:
        await _read("big.txt:100-110")
        big_file.write_text(big_file.read_text(encoding="utf-8").replace("line 105\n", "line 105 by someone else\n"))

        with pytest.raises(ToolError, match=r"changed on disk"):
            await _edit("big.txt", "line 105 by someone else\n", "LINE 105\n")

    async def test_a_range_read_after_an_outside_change_refreshes_the_record(self, big_file: Path) -> None:
        await _read("big.txt")
        big_file.write_text(big_file.read_text(encoding="utf-8").replace("line 250\n", "line 250 by someone else\n"))
        await _read("big.txt:100-110")

        await _edit("big.txt", "line 105\n", "LINE 105\n")

        assert "LINE 105" in big_file.read_text(encoding="utf-8")


class TestWithoutAReadTheEditIsRefused:
    async def test_a_file_never_read(self, big_file: Path) -> None:
        with pytest.raises(ToolError, match=r"has not been read"):
            await _edit("big.txt", "line 105\n", "LINE 105\n")

    @pytest.mark.parametrize("mode", ["preview", "stream"])
    async def test_a_preview_or_stream_read_does_not_count_even_for_the_same_absolute_path(
        self, big_file: Path, mode: str
    ) -> None:
        await _read(str(big_file), mode=mode)

        with pytest.raises(ToolError, match=r"has not been read"):
            await _edit(str(big_file), "line 5\n", "LINE 5\n")


class TestAfterAFullRead:
    async def test_an_edit_succeeds(self, big_file: Path) -> None:
        await _read("big.txt")

        await _edit("big.txt", "line 105\n", "LINE 105\n")

        assert "LINE 105" in big_file.read_text(encoding="utf-8")
