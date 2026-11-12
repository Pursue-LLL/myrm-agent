"""Architecture test: the open-source tree tracks no symlinks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SYMLINK_MODE = "120000"


def _tracked_symlinks(repo: Path) -> list[str]:
    """Return the staged paths whose git file mode is a symlink (``git ls-files -s`` rows: ``mode blob stage<TAB>path``)."""
    listing = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=repo, capture_output=True, check=True)
    rows = (row.decode("utf-8", errors="replace") for row in listing.stdout.split(b"\0") if row)
    return [row.partition("\t")[2] for row in rows if row.startswith(f"{_SYMLINK_MODE} ")]


def test_the_tree_tracks_no_symlinks() -> None:
    # A link target is a path on the machine that committed it. Tracked, it breaks fresh checkouts (a
    # committed `.venv` link makes `uv sync` stop with "File exists") and Windows or archive-based builds.
    # The usual cause is a link a worktree uses to share a virtualenv or node_modules, picked up by `git add -A`.
    assert _tracked_symlinks(_REPO_ROOT) == []


@pytest.mark.skipif(sys.platform == "win32", reason="creating a symlink needs a privilege Windows runners lack")
def test_detector_reports_a_staged_symlink_and_not_a_regular_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "plain.txt").write_text("content\n", encoding="utf-8")
    (tmp_path / "linked").symlink_to("/nonexistent/target")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert _tracked_symlinks(tmp_path) == ["linked"]
