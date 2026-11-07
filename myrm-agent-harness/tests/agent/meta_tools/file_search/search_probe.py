"""Helpers for driving glob_tool and grep_tool against real directory trees in the file_search suites."""

from __future__ import annotations

import itertools
import logging
import subprocess
import types
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import fallback_search, glob_tool, grep_tool

SearchRunner = Callable[..., Awaitable[str]]

# Fails a hung search instead of the whole suite.
SEARCH_TIMEOUT_GUARD_SECONDS = 20.0


def write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def git(root: Path, *arguments: str, check: bool = True) -> str:
    """Run git in ``root`` under a fixed identity and return its stdout.

    ``check=False`` tolerates a failing exit status, such as a merge that stops on a conflict.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "protocol.file.allow=always",
            *arguments,
        ],
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def end_time_budget_after(monkeypatch: pytest.MonkeyPatch, batches: int) -> None:
    """Make the Python tier's time budget run out once ``batches`` batches of files have been searched.

    The tier reads the clock once to start the budget and once before each batch.
    """
    reads = itertools.count()
    clock = types.SimpleNamespace(monotonic=lambda: 0.0 if next(reads) <= batches else 100.0)
    monkeypatch.setattr(fallback_search, "time", clock)


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


def warnings_from(caplog: pytest.LogCaptureFixture, module: types.ModuleType) -> list[str]:
    """What `module` logged at WARNING level or above, the levels a production process keeps, one text per record."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == module.__name__ and record.levelno >= logging.WARNING
    ]
