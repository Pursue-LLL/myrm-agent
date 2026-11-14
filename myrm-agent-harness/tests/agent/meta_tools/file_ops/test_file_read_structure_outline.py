"""``parse_mode='structure'`` outlines the whole file it scans, and says where the outline stops when it cannot.

Runs the real chain: ``file_read_tool`` through a ``LocalExecutor`` on real files. The outline used to be cut from the
text the page cap (``max_read_chars``) leaves, so a file past a few hundred lines got an outline of its first
screenful with nothing to say it was partial.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

_CONTINUES = "the file continues"


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    root_token = workspace_root_var.set(str(root))
    try:
        yield root
    finally:
        workspace_root_var.reset(root_token)
        reset_executor(executor_token)


async def _read(args: dict[str, object]) -> str:
    return str(await create_file_read_tool().ainvoke(args, config=RunnableConfig()))


async def _outline(name: str) -> str:
    return await _read({"paths": [name], "parse_mode": "structure"})


def _markdown(sections: int) -> str:
    return "".join(f"## Section {i:03d}\n\n{'filler text. ' * 30}\n\n" for i in range(1, sections + 1))


def _python(functions: int) -> str:
    return "".join(
        f"def func_{i:03d}(a, b):\n    # {'padding ' * 25}\n    return a + b\n\n\n" for i in range(1, functions + 1)
    )


def _typescript(functions: int) -> str:
    return "".join(
        f"export function fn_{i:03d}(): number {{\n  // {'padding ' * 25}\n  return {i};\n}}\n\n"
        for i in range(1, functions + 1)
    )


_SERVICE = """import os


class Service:
    def start(self):
        return 1

    async def stop(self):
        return 2


def helper():
    return 3
"""


def _lines(count: int, headings: dict[int, str]) -> str:
    """``count`` lines of filler, except the headings at the given line numbers."""
    return "\n".join(headings.get(i, f"filler {i}") for i in range(1, count + 1))


class TestOutlineOfAFilePastThePageCap:
    @pytest.mark.parametrize(
        ("name", "build", "count", "first", "last"),
        [
            ("mod.py", _python, 90, "def func_001", "def func_090"),
            ("mod.ts", _typescript, 90, "function fn_001", "function fn_090"),
            ("doc.md", _markdown, 80, "## Section 001", "## Section 080"),
        ],
        ids=["python", "typescript", "markdown"],
    )
    async def test_every_symbol_of_the_file_is_listed_not_just_those_of_its_first_page(
        self, workspace: Path, name: str, build: Callable[[int], str], count: int, first: str, last: str
    ) -> None:
        text = build(count)
        (workspace / name).write_text(text)
        assert len(text) > 2 * DEFAULT_FILE_IO_CONFIG.max_read_chars

        out = await _outline(name)

        assert first in out
        assert last in out
        assert "more symbols" not in out
        assert _CONTINUES not in out

    async def test_the_outline_is_not_reported_as_a_truncated_read(self, workspace: Path) -> None:
        (workspace / "doc.md").write_text(_markdown(80))
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths._dispatch_truncation_event",
            new_callable=AsyncMock,
        ) as dispatched:
            await _outline("doc.md")

        dispatched.assert_not_awaited()


class TestOutlineOfWhatAReadShows:
    """The outline is built from the view the service renders: a notice and tags around the numbered lines."""

    async def test_python_symbols_have_ranges_and_methods_are_named_after_their_class(self, workspace: Path) -> None:
        (workspace / "mod.py").write_text(_SERVICE)

        out = await _outline("mod.py")

        assert out.splitlines()[1:] == [
            "  - Line 4-9: class Service",
            "  - Line 5-6: def Service.start",
            "  - Line 8-9: async def Service.stop",
            "  - Line 12-13: def helper",
        ]

    async def test_a_yaml_comment_in_the_frontmatter_is_not_a_heading(self, workspace: Path) -> None:
        (workspace / "doc.md").write_text("---\ntitle: T\n# a yaml comment\n---\n\n# Real heading\n\n## Second\n")

        out = await _outline("doc.md")

        assert out.splitlines()[1:] == ["  - Line 6: # Real heading", "  - Line 8: ## Second"]

    async def test_the_rest_of_a_truncated_python_read_is_outlined_with_ranges(self, workspace: Path) -> None:
        padding = 120
        tail = "class Tail:\n    def last(self):\n        return 9\n\n\ndef tail_fn():\n    return 1\n"
        text = "".join(f"# {'padding ' * 25}\n" for _ in range(padding)) + tail
        (workspace / "mod.py").write_text(text)
        assert len(text) > 2 * DEFAULT_FILE_IO_CONFIG.max_read_chars

        out = await _read({"paths": ["mod.py"]})

        assert out.splitlines()[-3:] == [
            f"  - Line {padding + 1}-{padding + 3}: class Tail",
            f"  - Line {padding + 2}-{padding + 3}: def Tail.last",
            f"  - Line {padding + 6}-{padding + 7}: def tail_fn",
        ]


class TestOutlineOfAFilePastTheScanCap:
    async def test_the_outline_names_the_line_it_stops_at_and_how_to_read_on(self, workspace: Path) -> None:
        headings = {1: "# Top", 4900: "## Late", 5600: "## Beyond the scan"}
        (workspace / "long.md").write_text(_lines(6000, headings))

        out = await _outline("long.md")

        assert "Line 4900: ## Late" in out
        assert "Beyond the scan" not in out
        stop = re.search(rf"stops at line (\d+); {_CONTINUES}\. Read on with 'long\.md:(\d+)-'", out)
        assert stop is not None
        last_scanned, next_line = int(stop.group(1)), int(stop.group(2))
        assert next_line == last_scanned + 1
        assert 4900 <= last_scanned < 5600

        rest = await _read({"paths": [f"long.md:{next_line}-{next_line}"]})
        assert f"filler {next_line}" in rest
        assert f"filler {last_scanned}" not in rest

    async def test_a_long_file_without_symbols_still_says_it_was_not_scanned_to_the_end(self, workspace: Path) -> None:
        (workspace / "plain.md").write_text(_lines(6000, {}))

        out = await _outline("plain.md")

        assert "No structural symbols detected" in out
        assert _CONTINUES in out

    async def test_no_size_leaves_a_symbol_off_the_outline_without_saying_so(self, workspace: Path) -> None:
        """Around the scan cap, the last heading is either listed or the outline says the file continues; never neither."""
        listed_sizes: list[int] = []
        noted_sizes: list[int] = []
        for size in range(4990, 5006):
            (workspace / "edge.md").write_text(_lines(size, {1: "# Top", size: "# Last"}) + "\n")
            out = await _outline("edge.md")
            listed = f"Line {size}: # Last" in out
            noted = _CONTINUES in out
            assert listed != noted, f"size {size}: listed={listed} noted={noted}"
            (listed_sizes if listed else noted_sizes).append(size)

        assert listed_sizes
        assert noted_sizes
        assert max(listed_sizes) + 1 == min(noted_sizes)
