"""Reading big files: a line range reaches any line, and ``stream`` hands over one bounded page, not the file."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.constants import (
    MAX_FILE_READ_SIZE_BYTES,
    MAX_RANGED_READ_SIZE_BYTES,
)
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.meta_tools.file_ops.streaming import read_file_chunked
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

_LINES = 120_000  # ~12 MB at 100 bytes a line: past the plain read limit, far below the ranged one


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    (root / "big.log").write_text("".join(f"line {i} " + "x" * 90 + "\n" for i in range(_LINES)))
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    root_token = workspace_root_var.set(str(root))
    try:
        yield root
    finally:
        workspace_root_var.reset(root_token)
        reset_executor(executor_token)


async def _read(args: dict[str, object]) -> str:
    return str(await create_file_read_tool().ainvoke(args, config=RunnableConfig()))


class TestRangedRead:
    async def test_a_line_range_reaches_any_line_of_a_file_past_the_plain_limit(self, workspace: Path) -> None:
        assert (workspace / "big.log").stat().st_size > MAX_FILE_READ_SIZE_BYTES
        out = await _read({"paths": ["big.log:60000-60001"]})
        assert "line 59999 " in out
        assert "line 60000 " in out
        assert "line 60001 " not in out
        assert "File too large" not in out

    async def test_a_whole_file_read_past_the_plain_limit_points_to_the_line_range(self, workspace: Path) -> None:
        out = await _read({"paths": ["big.log"]})
        assert "File too large" in out
        assert "line range" in out

    async def test_a_range_past_the_ranged_limit_points_to_search_instead(self, workspace: Path) -> None:
        with (workspace / "huge.log").open("wb") as f:
            f.truncate(MAX_RANGED_READ_SIZE_BYTES + 1)  # sparse: nothing is written, nothing is read
        out = await _read({"paths": ["huge.log:1-3"]})
        assert "File too large" in out
        assert "grep_tool" in out
        assert "line range syntax" not in out


class TestStreamPage:
    async def test_stream_hands_over_one_bounded_page_quickly(self, workspace: Path) -> None:
        started = time.monotonic()
        out = await _read({"paths": ["big.log"], "mode": "stream"})
        assert time.monotonic() - started < 5
        assert len(out) < (workspace / "big.log").stat().st_size / 10
        assert "file continues" in out

    async def test_the_continuation_range_starts_on_the_line_after_the_page(self, workspace: Path) -> None:
        out = await _read({"paths": ["big.log"], "mode": "stream"})
        match = re.search(r"big\.log:(\d+)-(\d+)'", out)
        assert match is not None
        first_unseen = int(match.group(1))
        assert f"line {first_unseen - 2} " in out  # the last shown line (1-based line N is "line N-1")
        assert f"line {first_unseen - 1} " not in out
        assert int(match.group(2)) > first_unseen

        rest = await _read({"paths": [f"big.log:{first_unseen}-{first_unseen}"]})
        assert f"line {first_unseen - 1} " in rest

    async def test_a_small_file_streams_whole(self, workspace: Path) -> None:
        (workspace / "small.txt").write_text("".join(f"row {i}\n" for i in range(100)))
        out = await _read({"paths": ["small.txt"], "mode": "stream"})
        assert "row 0\n" in out
        assert "row 99" in out
        assert "file continues" not in out

    async def test_one_line_longer_than_a_page_points_to_search(self, workspace: Path) -> None:
        (workspace / "min.json").write_text("x" * 3_000_000)
        out = await _read({"paths": ["min.json"], "mode": "stream"})
        assert "first line alone fills a page" in out
        assert "grep_tool" in out
        assert len(out) < 100_000


class TestReadFileChunked:
    async def test_stops_one_character_past_max_chars(self, tmp_path: Path) -> None:
        path = tmp_path / "t.txt"
        path.write_text("a" * 5000)
        assert len(await read_file_chunked(path, max_chars=1000)) == 1001

    async def test_a_file_within_max_chars_is_read_whole(self, tmp_path: Path) -> None:
        path = tmp_path / "t.txt"
        path.write_text("a" * 500)
        assert await read_file_chunked(path, max_chars=1000) == "a" * 500

    async def test_without_max_chars_the_whole_file_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "t.txt"
        path.write_text("a" * 5000)
        assert len(await read_file_chunked(path)) == 5000
