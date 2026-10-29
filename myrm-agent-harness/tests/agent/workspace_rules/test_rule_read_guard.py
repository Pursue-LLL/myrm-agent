"""Tests for the boundary check and the read budgets of one workspace rule scan.

[INPUT]
- agent.workspace_rules.rule_read_guard::RuleReadGuard, RuleRead and the limits (POS: boundary-checked, bounded reads of rule files)
- real files and symlinks in a temp directory (POS: the file system decides what resolves where; nothing is faked)

[OUTPUT]
- Fails when a file whose real path leaves the boundary is read, when a read is not bounded, when a read that fits is not byte for byte what
  ``Path.read_text`` returns, or when a budget is exceeded, charged wrongly, or exhausted without one warning.

[POS]
Pins the guard in isolation; ``test_hostile_workspace.py`` pins the scanner, the middleware and the tracker that use it.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import IO

import pytest

from myrm_agent_harness.agent.workspace_rules import rule_read_guard
from myrm_agent_harness.agent.workspace_rules.rule_read_guard import (
    MAX_REFUSAL_NOTES,
    MAX_RULE_CHARS_PER_SCAN,
    MAX_RULE_FILE_READ_CHARS,
    MAX_RULE_FILES_PER_SCAN,
    RuleRead,
    RuleReadGuard,
)


@pytest.fixture(autouse=True)
def _forget_warned_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """Which refusals this process has already warned about is process-wide state; every test starts without any."""
    monkeypatch.setattr(rule_read_guard, "_remembered_events", set())


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture()
def outside(tmp_path: Path) -> Path:
    directory = tmp_path / "outside"
    directory.mkdir()
    (directory / "secret.md").write_text("OUTSIDE_SECRET api_token=abc123\n")
    return directory


@pytest.fixture()
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Names of the files opened for reading through ``Path.open`` (which is also what ``Path.read_text`` goes through)."""
    names: list[str] = []
    real_open: Callable[..., object] = Path.open

    def recording(self: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        if "r" in mode:
            names.append(self.name)
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording)
    return names


@pytest.fixture()
def read_sizes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The size argument of every ``read`` on a file opened through ``Path.open``: -1 is a read of the whole file."""
    sizes: list[int] = []
    real_open: Callable[..., IO[str]] = Path.open

    class _Handle:
        def __init__(self, handle: IO[str]) -> None:
            self._handle = handle

        def __enter__(self) -> _Handle:
            self._handle.__enter__()
            return self

        def __exit__(
            self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
        ) -> None:
            self._handle.__exit__(exc_type, exc, tb)

        def read(self, size: int = -1) -> str:
            sizes.append(size)
            return self._handle.read(size)

        def write(self, text: str) -> int:
            return self._handle.write(text)

    def recording(self: Path, *args: object, **kwargs: object) -> _Handle:
        return _Handle(real_open(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", recording)
    return sizes


class TestLimitsSitAboveRealRepositories:
    def test_the_largest_repository_measured_fits(self) -> None:
        # Measured over the 293 open-source repositories whose scan reads rule files: at most 159 files, 114,618 characters in one file and
        # 377,804 characters in all.
        assert MAX_RULE_FILES_PER_SCAN >= 2 * 159
        assert MAX_RULE_FILE_READ_CHARS >= 2 * 114_618
        assert MAX_RULE_CHARS_PER_SCAN >= 2 * 377_804


class TestRead:
    def test_a_file_inside_the_boundary_is_read(self, repo: Path) -> None:
        (repo / "AGENTS.md").write_text("# Rules\n")

        assert RuleReadGuard(repo).read(repo / "AGENTS.md") == RuleRead(text="# Rules\n", refusal=None)

    def test_the_text_is_what_read_text_returns(self, repo: Path) -> None:
        path = repo / "AGENTS.md"
        path.write_bytes(b"one\r\ntwo\rthree\n\xff\xfe broken \xc3\n")

        assert RuleReadGuard(repo).read(path).text == path.read_text(encoding="utf-8", errors="replace")
        assert "\r" not in (RuleReadGuard(repo).read(path).text or "")

    def test_a_file_at_the_limit_is_read_whole(self, repo: Path) -> None:
        (repo / "AGENTS.md").write_text("x" * MAX_RULE_FILE_READ_CHARS)

        assert RuleReadGuard(repo).read(repo / "AGENTS.md").text == "x" * MAX_RULE_FILE_READ_CHARS

    def test_a_file_over_the_limit_is_refused(self, repo: Path) -> None:
        (repo / "AGENTS.md").write_text("x" * (MAX_RULE_FILE_READ_CHARS + 1))

        read = RuleReadGuard(repo).read(repo / "AGENTS.md")

        assert read.text is None
        assert read.refusal is not None
        assert str(MAX_RULE_FILE_READ_CHARS) in read.refusal

    def test_a_large_file_is_never_read_whole(self, repo: Path, read_sizes: list[int]) -> None:
        (repo / "AGENTS.md").write_text("x" * (3 * MAX_RULE_FILE_READ_CHARS))

        RuleReadGuard(repo).read(repo / "AGENTS.md")

        assert read_sizes == [MAX_RULE_FILE_READ_CHARS + 1]

    def test_a_missing_file_raises_like_read_text(self, repo: Path) -> None:
        with pytest.raises(OSError):
            RuleReadGuard(repo).read(repo / "missing.md")


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
class TestBoundary:
    def test_a_symlink_to_a_file_outside_is_refused_and_never_read(
        self, repo: Path, outside: Path, opened: list[str]
    ) -> None:
        (repo / "AGENTS.md").symlink_to(outside / "secret.md")

        read = RuleReadGuard(repo).read(repo / "AGENTS.md")

        assert read.text is None
        assert read.refusal is not None
        assert "outside" in read.refusal
        assert "OUTSIDE_SECRET" not in repr(read)
        assert opened == []

    def test_a_symlink_to_a_file_inside_is_read(self, repo: Path) -> None:
        (repo / "shared.md").write_text("shared rules\n")
        (repo / "AGENTS.md").symlink_to(repo / "shared.md")

        assert RuleReadGuard(repo).read(repo / "AGENTS.md").text == "shared rules\n"

    def test_a_symlinked_directory_that_leaves_the_boundary_is_refused(self, repo: Path, outside: Path) -> None:
        (repo / ".myrm").mkdir()
        (repo / ".myrm" / "rules").symlink_to(outside, target_is_directory=True)

        read = RuleReadGuard(repo).read(repo / ".myrm" / "rules" / "secret.md")

        assert read.text is None
        assert read.refusal is not None

    def test_a_dotdot_path_that_leaves_the_boundary_is_refused(self, repo: Path, outside: Path) -> None:
        read = RuleReadGuard(repo).read(repo / ".." / "outside" / "secret.md")

        assert read.text is None
        assert read.refusal is not None


class TestBudgets:
    def test_a_read_past_the_file_budget_does_not_open_the_file(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, opened: list[str]
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILES_PER_SCAN", 3)
        for index in range(5):
            (repo / f"r{index}.md").write_text("rule\n")
        guard = RuleReadGuard(repo)

        reads = [guard.read(repo / f"r{index}.md") for index in range(5)]

        assert [read.text for read in reads] == ["rule\n"] * 3 + [None, None]
        assert [read.refusal for read in reads[3:]] == [None, None]
        assert opened == ["r0.md", "r1.md", "r2.md"]

    @pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
    def test_a_refused_file_counts_against_the_file_budget(
        self, repo: Path, outside: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILES_PER_SCAN", 2)
        monkeypatch.setattr(rule_read_guard, "MAX_REFUSAL_NOTES", 10)
        (repo / "a.md").symlink_to(outside / "secret.md")
        (repo / "b.md").symlink_to(outside / "secret.md")
        (repo / "c.md").write_text("rule\n")
        guard = RuleReadGuard(repo)

        reads = [guard.read(repo / name) for name in ("a.md", "b.md", "c.md")]

        assert [read.text for read in reads] == [None, None, None]
        assert reads[2].refusal is None

    def test_the_character_budget_is_checked_before_each_read(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_CHARS_PER_SCAN", 100)
        for index in range(3):
            (repo / f"r{index}.md").write_text("x" * 60)
        guard = RuleReadGuard(repo)

        texts = [guard.read(repo / f"r{index}.md").text for index in range(3)]

        assert texts == ["x" * 60, "x" * 60, None]

    def test_a_file_over_the_limit_is_charged_for_what_was_read(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILE_READ_CHARS", 50)
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_CHARS_PER_SCAN", 40)
        (repo / "big.md").write_text("x" * 500)
        (repo / "small.md").write_text("rule\n")
        guard = RuleReadGuard(repo)

        assert guard.read(repo / "big.md").text is None
        assert guard.read(repo / "small.md") == RuleRead(text=None, refusal=None)

    @pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
    def test_only_the_first_refusals_carry_a_reason(self, repo: Path, outside: Path) -> None:
        for index in range(MAX_REFUSAL_NOTES + 2):
            (repo / f"r{index}.md").symlink_to(outside / "secret.md")
        guard = RuleReadGuard(repo)

        reasons = [guard.read(repo / f"r{index}.md").refusal for index in range(MAX_REFUSAL_NOTES + 2)]

        assert all(reasons[:MAX_REFUSAL_NOTES])
        assert reasons[MAX_REFUSAL_NOTES:] == [None, None]

    def test_running_out_of_budget_is_warned_once(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILES_PER_SCAN", 2)
        for index in range(6):
            (repo / f"r{index}.md").write_text("rule\n")
        guard = RuleReadGuard(repo)

        with caplog.at_level(logging.WARNING, logger=rule_read_guard.logger.name):
            for index in range(6):
                guard.read(repo / f"r{index}.md")

        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "stopped" in warnings[0].getMessage()

    def test_two_guards_do_not_share_a_budget(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILES_PER_SCAN", 1)
        (repo / "a.md").write_text("rule\n")

        assert RuleReadGuard(repo).read(repo / "a.md").text == "rule\n"
        assert RuleReadGuard(repo).read(repo / "a.md").text == "rule\n"


class TestWarningsAreNotRepeated:
    """A scan runs on every model call: a refusal that stays true is a warning once per process and a debug line after that."""

    def test_the_same_refusal_is_a_warning_once(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILE_READ_CHARS", 10)
        (repo / "big.md").write_text("x" * 50)

        with caplog.at_level(logging.DEBUG, logger=rule_read_guard.logger.name):
            for _ in range(3):
                RuleReadGuard(repo).read(repo / "big.md")

        assert [record.levelno for record in caplog.records] == [logging.WARNING, logging.DEBUG, logging.DEBUG]

    def test_another_file_is_warned_about_again(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILE_READ_CHARS", 10)
        (repo / "a.md").write_text("x" * 50)
        (repo / "b.md").write_text("x" * 50)

        with caplog.at_level(logging.DEBUG, logger=rule_read_guard.logger.name):
            RuleReadGuard(repo).read(repo / "a.md")
            RuleReadGuard(repo).read(repo / "b.md")

        assert [record.levelno for record in caplog.records] == [logging.WARNING, logging.WARNING]

    def test_running_out_of_budget_is_a_warning_once_across_scans(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILES_PER_SCAN", 1)
        (repo / "a.md").write_text("rule\n")
        (repo / "b.md").write_text("rule\n")

        with caplog.at_level(logging.DEBUG, logger=rule_read_guard.logger.name):
            for _ in range(2):
                guard = RuleReadGuard(repo)
                guard.read(repo / "a.md")
                guard.read(repo / "b.md")

        assert [record.levelno for record in caplog.records] == [logging.WARNING, logging.DEBUG]

    def test_what_is_remembered_is_bounded(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rule_read_guard, "_MAX_REMEMBERED_EVENTS", 2)
        monkeypatch.setattr(rule_read_guard, "MAX_RULE_FILE_READ_CHARS", 10)
        for index in range(5):
            (repo / f"r{index}.md").write_text("x" * 50)
            RuleReadGuard(repo).read(repo / f"r{index}.md")

        assert len(rule_read_guard._remembered_events) <= 2
