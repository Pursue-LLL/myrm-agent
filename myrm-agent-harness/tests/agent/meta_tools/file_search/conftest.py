"""Fixtures shared by the file_search suites."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

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


@pytest.fixture(params=["ripgrep", "python"])
def engine(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Select the search tier by controlling ripgrep detection.

    A test that only makes sense on one tier narrows it with
    ``@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)``.
    """
    use_ripgrep = request.param == "ripgrep"
    if use_ripgrep:
        request.getfixturevalue("require_ripgrep")
    monkeypatch.setattr(grep_tool, "_has_ripgrep", lambda: use_ripgrep)
    return str(request.param)


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
