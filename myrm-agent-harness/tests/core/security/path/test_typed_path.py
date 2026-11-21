"""The file a typed path opens: one reading for the permission engine, the grant flow and the respelling probe.

A bare ``~`` is the user's home and nothing else is expanded, a relative spelling lies below the workspace, and every
link in the path is followed. A text no file can be named by opens nothing, so a gate refuses it instead of raising.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.path import opened_path
from myrm_agent_harness.core.security.path.typed_path import spelled_path

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="links and escape-encoded names are POSIX behaviour")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "home"
    directory.mkdir()
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(directory))
    return directory


def test_a_bare_tilde_is_the_users_home(workspace: Path, home: Path) -> None:
    assert spelled_path("~/notes.txt", str(workspace)) == str(home / "notes.txt")
    assert opened_path("~/notes.txt", str(workspace)) == os.path.realpath(home / "notes.txt")


@pytest.mark.parametrize("typed", ["$MYRM_UP/notes.txt", "~root/notes.txt", "~$notes.txt"])
def test_every_other_spelling_is_a_name_below_the_workspace(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, typed: str
) -> None:
    monkeypatch.setenv("MYRM_UP", "../elsewhere")

    assert spelled_path(typed, str(workspace)) == os.path.join(workspace, typed)
    assert opened_path(typed, str(workspace)) == os.path.realpath(os.path.join(workspace, typed))


def test_an_absolute_path_ignores_the_workspace(workspace: Path, tmp_path: Path) -> None:
    elsewhere = str(tmp_path / "elsewhere" / "a.txt")

    assert spelled_path(elsewhere, str(workspace)) == elsewhere


def test_without_a_workspace_a_relative_path_stays_relative() -> None:
    assert spelled_path("src/a.py", None) == "src/a.py"
    assert opened_path("src/a.py", None) == os.path.realpath("src/a.py")


@POSIX_ONLY
def test_every_link_is_followed_by_the_opened_path_and_not_by_the_spelled_one(workspace: Path) -> None:
    (workspace / ".env").write_text("CANARY=1")
    (workspace / "notes.txt").symlink_to(".env")

    assert spelled_path("notes.txt", str(workspace)) == str(workspace / "notes.txt")
    assert opened_path("notes.txt", str(workspace)) == os.path.realpath(workspace / ".env")


@POSIX_ONLY
def test_a_link_named_like_a_variable_is_followed_and_not_expanded(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_LINKED", "expanded")
    (workspace / ".env").write_text("CANARY=1")
    (workspace / "$MYRM_LINKED").symlink_to(".env")

    assert opened_path("$MYRM_LINKED", str(workspace)) == os.path.realpath(workspace / ".env")


@pytest.mark.parametrize("text", ["a\x00b", "a\ud800b"], ids=["nul-byte", "lone-surrogate"])
def test_a_text_no_file_can_be_named_by_opens_nothing(workspace: Path, text: str) -> None:
    assert opened_path(text, str(workspace)) is None


@POSIX_ONLY
def test_a_byte_that_file_names_carry_as_an_escape_is_a_resolvable_name(workspace: Path) -> None:
    # ``os.fsdecode`` reads a byte that is no UTF-8 as U+DC80..U+DCFF, so such a name is an ordinary file name.
    name = "a\udc80b"

    assert opened_path(name, str(workspace)) == os.path.realpath(os.path.join(workspace, name))
