"""Helpers for driving glob_tool and grep_tool against real directory trees in the file_search suites."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import glob_tool, grep_tool

SearchRunner = Callable[..., Awaitable[str]]

# Fails a hung search instead of the whole suite.
SEARCH_TIMEOUT_GUARD_SECONDS = 20.0


def write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def bind_executor(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Make both tools resolve paths against ``root`` as the workspace."""
    executor = AsyncMock()

    async def resolve_path(path: str) -> str:
        return str(root) if path == "." else str(root / path)

    executor.resolve_path = resolve_path
    monkeypatch.setattr(glob_tool, "ensure_executor", lambda _config: executor)
    monkeypatch.setattr(grep_tool, "ensure_executor", lambda _config: executor)


def listed(output: str) -> set[str]:
    """The paths a glob_tool result lists."""
    return {line.strip() for line in output.splitlines() if line.startswith(" ") and line.strip()}


def hit_files(output: str, candidates: set[str]) -> set[str]:
    """The candidates that appear in a grep_tool result."""
    return {candidate for candidate in candidates if candidate in output}
