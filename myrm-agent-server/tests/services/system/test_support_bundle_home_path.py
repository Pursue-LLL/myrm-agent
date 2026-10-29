"""A bundle is made to be shared, so the home folder, which carries the account name, is written as ``~`` everywhere.

The folder is replaced as the operating system spells it, with the doubled backslashes of a JSON string and with
forward slashes; a longer name that merely starts with it is left alone. The one place that never saw a redactor, the
placeholder for a log that could not be read, goes through the same exit as every other piece of text.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config.settings import DatabaseSettings
from app.services.system.support_bundle_service import SupportBundleService, _home_forms, _safe_json_dumps, _scrub

_MODULE = "app.services.system.support_bundle_service"
_SECRET = "sk-proj-Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zA7bC0dE3fG6hJ9kL"


def _home_is(monkeypatch: pytest.MonkeyPatch, home: PurePath) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


class TestHomeForms:
    def test_a_posix_home_is_written_one_way(self) -> None:
        assert _home_forms(PurePosixPath("/Users/ann")) == ("/Users/ann",)

    def test_a_windows_home_is_written_three_ways_longest_first(self) -> None:
        assert _home_forms(PureWindowsPath("C:\\Users\\ann")) == (
            "C:\\\\Users\\\\ann",
            "C:/Users/ann",
            "C:\\Users\\ann",
        )

    @pytest.mark.parametrize("home", [PurePosixPath("/"), PurePosixPath(""), PureWindowsPath("")])
    def test_a_root_or_empty_home_names_nobody_and_is_not_replaced(self, home: PurePath) -> None:
        assert _home_forms(home) == ()


class TestHomeFolderIsReplaced:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("opened /Users/ann/.myrm/app.db", "opened ~/.myrm/app.db"),
            ("cwd=/Users/ann", "cwd=~"),
            ('{"path": "/Users/ann/work"}', '{"path": "~/work"}'),
            ("file:///Users/ann/x", "file://~/x"),
            ("/Users/ann,/Users/ann/x", "~,~/x"),
            ("'/Users/ann'", "'~'"),
        ],
    )
    def test_a_posix_home_becomes_a_tilde(self, monkeypatch: pytest.MonkeyPatch, text: str, expected: str) -> None:
        _home_is(monkeypatch, PurePosixPath("/Users/ann"))
        assert _scrub(text) == expected

    @pytest.mark.parametrize(
        "text",
        ["/Users/ann2/x", "/Users/anna", "/Users/ann.bak", "/Users/ann-old/x", "/tmp/Users/ann/x", "Users/ann", "/Users/an"],
    )
    def test_a_longer_name_that_starts_with_the_home_is_left_alone(self, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
        _home_is(monkeypatch, PurePosixPath("/Users/ann"))
        assert _scrub(text) == text

    def test_a_windows_home_is_replaced_as_written_in_a_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _home_is(monkeypatch, PureWindowsPath("C:\\Users\\ann"))
        assert _scrub("C:\\Users\\ann\\proj") == "~\\proj"

    def test_a_windows_home_is_replaced_inside_a_json_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _home_is(monkeypatch, PureWindowsPath("C:\\Users\\ann"))
        scrubbed = _scrub(json.dumps({"path": "C:\\Users\\ann\\proj"}))
        assert "ann" not in scrubbed
        assert json.loads(scrubbed) == {"path": "~\\proj"}

    def test_a_windows_home_is_replaced_with_forward_slashes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _home_is(monkeypatch, PureWindowsPath("C:\\Users\\ann"))
        assert _scrub("C:/Users/ann/proj") == "~/proj"

    def test_a_home_that_is_the_root_leaves_every_path_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _home_is(monkeypatch, PurePosixPath("/"))
        assert _scrub("/usr/bin/python") == "/usr/bin/python"

    def test_an_unknown_home_leaves_the_text_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def no_home(cls: type[Path]) -> Path:
            raise RuntimeError("Could not determine home directory.")

        monkeypatch.setattr(Path, "home", classmethod(no_home))
        assert _scrub("/Users/ann/x") == "/Users/ann/x"

    def test_credentials_are_masked_in_the_same_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _home_is(monkeypatch, PurePosixPath("/Users/ann"))
        scrubbed = _scrub(f"key {_SECRET} read from /Users/ann/.env")
        assert _SECRET not in scrubbed
        assert scrubbed.endswith("read from ~/.env")

    def test_the_json_sections_of_a_bundle_use_the_same_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _home_is(monkeypatch, PurePosixPath("/Users/ann"))
        assert json.loads(_safe_json_dumps({"workspace": "/Users/ann/.myrm"})) == {"workspace": "~/.myrm"}


class TestEventTraces:
    @pytest.fixture
    def event_logs(self, tmp_path: Path) -> Path:
        logs = tmp_path / "event_logs"
        logs.mkdir()
        database = DatabaseSettings.model_construct(_fields_set=None, state_dir=str(tmp_path), event_log_dir=str(logs))
        with patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(database=database)):
            yield logs

    def test_a_home_path_inside_a_logged_command_is_replaced(self, monkeypatch: pytest.MonkeyPatch, event_logs: Path) -> None:
        _home_is(monkeypatch, PurePosixPath("/Users/ann"))
        event = {"seq": 1, "ts": 1.0, "type": "bash_command_executed", "sid": "s", "data": {"command": "ls /Users/ann/proj"}}
        (event_logs / "s.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

        trace = SupportBundleService.collect_recent_event_traces()["s.jsonl"]

        assert json.loads(trace)["data"]["command"] == "ls ~/proj"

    @pytest.mark.skipif(
        sys.platform == "win32" or not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs a file the user cannot read"
    )
    def test_a_log_that_cannot_be_read_is_reported_without_the_home_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, event_logs: Path
    ) -> None:
        _home_is(monkeypatch, tmp_path)
        locked = event_logs / "locked.jsonl"
        locked.write_text("{}\n", encoding="utf-8")
        locked.chmod(0)
        try:
            trace = SupportBundleService.collect_recent_event_traces()["locked.jsonl"]
        finally:
            locked.chmod(0o600)

        assert trace.startswith("[Read error:")
        assert str(tmp_path) not in trace
        assert "~/event_logs/locked.jsonl" in trace
