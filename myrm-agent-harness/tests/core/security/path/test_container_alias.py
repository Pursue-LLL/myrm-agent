"""The ``/workspace`` container alias is part of how a typed path is read.

The sandbox shows the agent its workspace as ``/workspace``, and the file tools open ``/workspace/x`` as
``<workspace>/x``. Every gate that judges a typed path reads it through ``spelled_path`` and ``opened_path``, so the
alias has to be resolved there: a rule, a zone and a grant must see the file the tool opens, not a directory that
happens to be called ``/workspace`` on the host.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.path import container_relative, opened_path
from myrm_agent_harness.core.security.path.typed_path import spelled_path

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="links are POSIX behaviour")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/workspace", "."),
        ("/workspace/", "."),
        ("/workspace/src/app.py", "src/app.py"),
        ("/workspace//src/app.py", "src/app.py"),
        ("/workspace2/src/app.py", None),
        ("/workspaces/a", None),
        ("workspace/src", None),
        ("src/app.py", None),
        ("/etc/passwd", None),
    ],
)
def test_the_alias_is_matched_by_whole_path_segments(path: str, expected: str | None) -> None:
    assert container_relative(path) == expected


@pytest.mark.parametrize(
    ("typed", "below_workspace"),
    [
        ("/workspace/src/app.py", "src/app.py"),
        ("/workspace//src/app.py", "src/app.py"),
        ("/workspace", "."),
    ],
)
def test_the_alias_is_the_workspace_in_the_spelled_and_the_opened_path(
    workspace: Path, typed: str, below_workspace: str
) -> None:
    assert spelled_path(typed, str(workspace)) == os.path.join(workspace, below_workspace)
    assert opened_path(typed, str(workspace)) == os.path.realpath(workspace / below_workspace)


def test_a_look_alike_of_the_alias_is_another_absolute_path(workspace: Path) -> None:
    assert spelled_path("/workspace2/app.py", str(workspace)) == "/workspace2/app.py"


def test_without_a_workspace_the_alias_is_an_ordinary_absolute_path() -> None:
    assert spelled_path("/workspace/app.py", None) == "/workspace/app.py"


@POSIX_ONLY
def test_a_link_below_the_alias_is_followed(workspace: Path) -> None:
    (workspace / ".env").write_text("CANARY=1")
    (workspace / "notes.txt").symlink_to(".env")

    assert opened_path("/workspace/notes.txt", str(workspace)) == os.path.realpath(workspace / ".env")
