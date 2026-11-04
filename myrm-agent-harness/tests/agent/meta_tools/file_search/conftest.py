"""Fixtures shared by the file_search suites."""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import NoReturn
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import FileIOConfig
from myrm_agent_harness.agent.meta_tools.file_search import glob_tool, grep_tool
from tests.agent.meta_tools.file_search.search_probe import (
    SEARCH_TIMEOUT_GUARD_SECONDS,
    SearchRunner,
    bind_executor,
)


@pytest.fixture
def require_ripgrep() -> None:
    """Skip without ripgrep locally; fail under CI, where a skip would silently drop every ripgrep-tier check."""
    if shutil.which("rg") is not None:
        return
    if os.environ.get("CI"):
        pytest.fail("ripgrep is missing: the CI job must install it (see 'Ensure ripgrep' in harness-test.yml)")
    pytest.skip("ripgrep not installed")


@pytest.fixture
def require_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git not installed")


@pytest.fixture
def plain_dir(tmp_path: Path) -> Path:
    """A temporary directory with no ``.git`` above it, so ignore-file semantics are those of a plain folder."""
    if any((candidate / ".git").exists() for candidate in (tmp_path, *tmp_path.parents)):
        pytest.skip("temporary directory lies inside a git repository")
    return tmp_path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A temporary workspace with the files the grep_tool tests search; a module that needs another tree overrides it."""
    (tmp_path / "hello.py").write_text("def hello():\n    return 42\n\ndef world():\n    pass\n")
    (tmp_path / "config.json").write_text('{"key": "value", "count": 1}\n')
    (tmp_path / "empty.txt").write_text("")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.py").write_text("import os\nimport sys\n")
    return tmp_path


@pytest.fixture
def mock_executor(workspace: Path) -> MagicMock:
    """Create a mock executor with resolve_path returning workspace paths."""
    executor = AsyncMock()

    async def _resolve_path(p: str) -> str:
        if p == ".":
            return str(workspace)
        return str(workspace / p)

    executor.resolve_path = _resolve_path
    return executor


@pytest.fixture
def runnable_config() -> RunnableConfig:
    return RunnableConfig(configurable={})


@pytest.fixture(params=["ripgrep", "python"])
def engine(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Select the search tier by controlling ripgrep detection.

    A test that only makes sense on one tier narrows it with
    ``@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)``.

    On the python tier ripgrep is also refused: a tool that stopped following the detection would otherwise search
    with ripgrep and its test would still pass, so the test fails when either tool tried to start it.
    """
    use_ripgrep = request.param == "ripgrep"
    if use_ripgrep:
        request.getfixturevalue("require_ripgrep")
    monkeypatch.setattr(grep_tool, "_has_ripgrep", lambda: use_ripgrep)

    refused: list[list[str]] = []

    async def refuse_ripgrep(cmd: Sequence[str], **_kwargs: object) -> NoReturn:
        # Recorded as well as raised: on a ripgrep error both tools fall back to the Python tier and would hide it.
        refused.append(list(cmd))
        raise OSError("the python tier must not start ripgrep")

    if not use_ripgrep:
        monkeypatch.setattr(grep_tool, "run_rg", refuse_ripgrep)
        monkeypatch.setattr(glob_tool, "run_rg", refuse_ripgrep)
    yield str(request.param)
    assert not refused, f"ripgrep was started while the python tier was selected: {refused}"


@pytest.fixture
def run_glob(engine: str, monkeypatch: pytest.MonkeyPatch) -> SearchRunner:
    async def invoke(
        root: Path,
        pattern: str,
        *,
        path: str = ".",
        include_ignored: bool = False,
        max_results: int = 100,
    ) -> str:
        bind_executor(monkeypatch, root)
        tool = glob_tool.create_glob_tool(FileIOConfig(max_search_results=max_results))
        return str(
            await asyncio.wait_for(
                tool.ainvoke(
                    {"pattern": pattern, "path": path, "include_ignored": include_ignored},
                    config=RunnableConfig(configurable={}),
                ),
                timeout=SEARCH_TIMEOUT_GUARD_SECONDS,
            )
        )

    return invoke


@pytest.fixture
def run_grep(engine: str, monkeypatch: pytest.MonkeyPatch) -> SearchRunner:
    async def invoke(
        root: Path,
        pattern: str,
        *,
        path: str = ".",
        file_pattern: str = "**/*",
        context_lines: int = 0,
        max_results: int = 100,
        max_files: int = 1000,
    ) -> str:
        bind_executor(monkeypatch, root)
        tool = grep_tool.create_grep_tool(FileIOConfig(max_search_results=max_results, max_search_files=max_files))
        output = await asyncio.wait_for(
            tool.ainvoke(
                {"pattern": pattern, "path": path, "file_pattern": file_pattern, "context_lines": context_lines},
                config=RunnableConfig(configurable={}),
            ),
            timeout=SEARCH_TIMEOUT_GUARD_SECONDS,
        )
        # The ripgrep tier prints absolute paths; compare on workspace-relative text.
        return str(output).replace(str(root) + "/", "")

    return invoke
