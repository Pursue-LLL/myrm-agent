"""Formatters that load code the workspace declares run only in a workspace the user trusts.

prettier executes ``prettier.config.js``, ``.prettierrc.js`` and the local plugins a JSON config names, and
``mix format`` executes ``.formatter.exs``. The agent's own sandbox can write those files without an approval, so
formatting after the write would run them on the host: the workspace trust gate has to cover it like it covers the
workspace's skills, rules and MCP servers.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers import format_observer
from myrm_agent_harness.agent.meta_tools.file_ops.observers.format_observer import (
    FORMATTER_RULES,
    FormatObserver,
    _FormatterCache,
)
from myrm_agent_harness.agent.security.workspace_trust import (
    WorkspaceTrustLevel,
    clear_workspace_trust_runtime,
    get_workspace_trust_lookup,
    set_workspace_trust_level,
    set_workspace_trust_lookup,
)
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

_NOT_TRUSTED: list[WorkspaceTrustLevel | None] = [None, WorkspaceTrustLevel.RESTRICTED, WorkspaceTrustLevel.REVOKED]

_Started = list[tuple[str, ...]]


class _Lookup:
    """One workspace, one decision; ``None`` is a folder the user has not decided about."""

    def __init__(self, root: Path, level: WorkspaceTrustLevel | None) -> None:
        self._root = str(root.resolve())
        self._level = level

    def normalize_path(self, raw_path: str) -> str:
        return str(Path(raw_path).resolve())

    def get_level(self, canonical_path: str) -> WorkspaceTrustLevel | None:
        return self._level if canonical_path == self._root else None

    def get_disclosed_command_prefixes(self, canonical_path: str) -> tuple[str, ...]:
        return ()


class _FinishedProcess:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


@pytest.fixture(autouse=True)
def _isolated_trust_state() -> Iterator[None]:
    previous = get_workspace_trust_lookup()
    yield
    set_workspace_trust_lookup(previous)
    clear_workspace_trust_runtime()


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "ws"
    root.mkdir()
    token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    yield root
    reset_executor(token)


@pytest.fixture
def every_formatter_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(format_observer, "_which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(format_observer, "_cache", _FormatterCache())


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch, every_formatter_is_installed: None) -> _Started:
    """The command line of every formatter process the observer starts."""
    calls: _Started = []

    async def fake_exec(*cmd: str, **_: object) -> _FinishedProcess:
        calls.append(cmd)
        return _FinishedProcess()

    monkeypatch.setattr(format_observer.asyncio, "create_subprocess_exec", fake_exec)
    return calls


def _decide(workspace: Path, level: WorkspaceTrustLevel | None) -> None:
    set_workspace_trust_lookup(_Lookup(workspace, level))


def _binaries(started: _Started) -> list[str]:
    return [cmd[0] for cmd in started]


# A file name per formatter that loads workspace code; ``prettier.config.js`` is the one that runs as a program.
_LOADS_WORKSPACE_CODE = [
    ("prettier.config.js", "prettier"),
    ("data.json", "prettier"),
    ("lib/app.ex", "mix"),
    ("mix.exs", "mix"),
]


class TestAWorkspaceTheUserDidNotTrust:
    @pytest.mark.parametrize("level", _NOT_TRUSTED)
    @pytest.mark.parametrize(("filename", "binary"), _LOADS_WORKSPACE_CODE)
    async def test_starts_no_formatter_that_loads_workspace_code(
        self, workspace: Path, started: _Started, filename: str, binary: str, level: WorkspaceTrustLevel | None
    ) -> None:
        _decide(workspace, level)

        await FormatObserver().on_file_created(str(workspace / filename), "")

        assert started == [], f"{binary} was started in a workspace the user has not trusted"

    @pytest.mark.parametrize(("filename", "binary"), _LOADS_WORKSPACE_CODE)
    async def test_the_same_holds_after_an_edit(
        self, workspace: Path, started: _Started, filename: str, binary: str
    ) -> None:
        _decide(workspace, WorkspaceTrustLevel.RESTRICTED)

        await FormatObserver().on_file_modified(str(workspace / filename), "old", "new")

        assert started == [], f"{binary} was started in a workspace the user has not trusted"

    async def test_no_decision_store_at_all_counts_as_not_trusted(self, workspace: Path, started: _Started) -> None:
        set_workspace_trust_lookup(None)

        await FormatObserver().on_file_created(str(workspace / "data.json"), "")

        assert started == []

    @pytest.mark.parametrize(
        ("filename", "binary"),
        [("app.py", "ruff"), ("main.go", "gofmt"), ("lib.rs", "rustfmt"), ("run.sh", "shfmt")],
    )
    async def test_still_runs_the_formatters_that_load_no_workspace_code(
        self, workspace: Path, started: _Started, filename: str, binary: str
    ) -> None:
        _decide(workspace, WorkspaceTrustLevel.RESTRICTED)

        await FormatObserver().on_file_created(str(workspace / filename), "")

        assert _binaries(started) == [binary]


class TestATrustedWorkspace:
    @pytest.mark.parametrize(("filename", "binary"), _LOADS_WORKSPACE_CODE)
    async def test_runs_the_formatter(self, workspace: Path, started: _Started, filename: str, binary: str) -> None:
        _decide(workspace, WorkspaceTrustLevel.TRUSTED)

        await FormatObserver().on_file_created(str(workspace / filename), "")

        assert _binaries(started) == [binary]

    async def test_a_trust_decision_covers_only_the_workspace_it_was_made_for(
        self, workspace: Path, started: _Started, tmp_path: Path
    ) -> None:
        other = tmp_path / "other"
        other.mkdir()
        _decide(other, WorkspaceTrustLevel.TRUSTED)

        await FormatObserver().on_file_created(str(workspace / "data.json"), "")

        assert started == []


class TestTheDecisionIsLookedUpByTheWorkspace:
    """LangGraph runs a tool body in a task that may not see the ContextVar the run bound at its start."""

    @pytest.mark.parametrize("bound", [None, WorkspaceTrustLevel.RESTRICTED])
    async def test_a_trusted_workspace_formats_whatever_the_runs_context_holds(
        self, workspace: Path, started: _Started, bound: WorkspaceTrustLevel | None
    ) -> None:
        _decide(workspace, WorkspaceTrustLevel.TRUSTED)
        set_workspace_trust_level(bound)

        await FormatObserver().on_file_created(str(workspace / "data.json"), "")

        assert _binaries(started) == ["prettier"]

    async def test_a_restricted_workspace_stays_restricted_whatever_the_runs_context_holds(
        self, workspace: Path, started: _Started
    ) -> None:
        _decide(workspace, WorkspaceTrustLevel.RESTRICTED)
        set_workspace_trust_level(WorkspaceTrustLevel.TRUSTED)

        await FormatObserver().on_file_created(str(workspace / "data.json"), "")

        assert started == []


class TestWithoutAnExecutor:
    """The workspace root comes from the executor; with none there is no folder to ask about."""

    async def test_starts_no_formatter_that_loads_workspace_code(self, tmp_path: Path, started: _Started) -> None:
        token = set_executor(None)
        try:
            _decide(tmp_path, WorkspaceTrustLevel.TRUSTED)

            await FormatObserver().on_file_created(str(tmp_path / "data.json"), "")
        finally:
            reset_executor(token)

        assert started == []

    async def test_still_runs_the_other_formatters(self, tmp_path: Path, started: _Started) -> None:
        token = set_executor(None)
        try:
            await FormatObserver().on_file_created(str(tmp_path / "app.py"), "")
        finally:
            reset_executor(token)

        assert _binaries(started) == ["ruff"]


def test_the_formatters_that_load_workspace_code_are_pinned() -> None:
    """A formatter added to the table is a conscious decision about whether it runs what the workspace declares."""
    flagged = {rule.bin_name for rule in FORMATTER_RULES if rule.loads_workspace_code}

    assert flagged == {"prettier", "mix"}


_STAND_IN_PRETTIER = """#!/bin/sh
echo "$@" > prettier_ran.txt
"""


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in formatter is a POSIX shell script")
class TestWithARealProcess:
    """A stand-in ``prettier`` on PATH leaves a marker in the directory it was started in."""

    @pytest.fixture(autouse=True)
    def _prettier_on_path(self, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
        bin_dir = tmp_path_factory.mktemp("formatter")
        prettier = bin_dir / "prettier"
        prettier.write_text(_STAND_IN_PRETTIER, encoding="utf-8")
        prettier.chmod(prettier.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setattr(format_observer, "_cache", _FormatterCache())

    async def test_a_prettier_config_written_into_an_untrusted_workspace_starts_no_prettier(
        self, workspace: Path
    ) -> None:
        _decide(workspace, WorkspaceTrustLevel.RESTRICTED)
        config = workspace / "prettier.config.js"
        config.write_text("module.exports = {};\n", encoding="utf-8")

        await FormatObserver().on_file_created(str(config), "module.exports = {};\n")

        assert not (workspace / "prettier_ran.txt").exists()

    async def test_the_same_write_into_a_trusted_workspace_starts_prettier_on_it(self, workspace: Path) -> None:
        _decide(workspace, WorkspaceTrustLevel.TRUSTED)
        config = workspace / "prettier.config.js"
        config.write_text("module.exports = {};\n", encoding="utf-8")

        await FormatObserver().on_file_created(str(config), "module.exports = {};\n")

        ran_with = (workspace / "prettier_ran.txt").read_text(encoding="utf-8")
        assert "--write" in ran_with
        assert config.name in ran_with
