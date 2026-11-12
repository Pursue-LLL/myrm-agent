"""Architecture test: the open-source tree tracks no symlinks, apart from the few in-repo links it lists."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SYMLINK_MODE = "120000"

# Links the tree ships on purpose. Each one is a relative link to a tracked regular file of this repository, in a tool
# that runs on Unix only, so a checkout without symlink support is not one the tool supports.
# - scripts/dev/chrome-agent/dev-ports.mjs keeps the Chrome Agent proxy on the single port SSOT in ../lib/ without a
#   copy that can drift; the installer's `cp -p` ships it as a regular file.
_ALLOWED_LINKS = frozenset({"scripts/dev/chrome-agent/dev-ports.mjs"})

_NO_SYMLINK_SUPPORT = "creating a symlink needs a privilege Windows runners lack"


def _tracked_symlinks(repo: Path) -> list[str]:
    """Return the staged paths whose git file mode is a symlink (``git ls-files -s`` rows: ``mode blob stage<TAB>path``)."""
    listing = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=repo, capture_output=True, check=True)
    rows = (row.decode("utf-8", errors="replace") for row in listing.stdout.split(b"\0") if row)
    return [row.partition("\t")[2] for row in rows if row.startswith(f"{_SYMLINK_MODE} ")]


def _tracked_paths(repo: Path) -> set[str]:
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True)
    return {row.decode("utf-8", errors="replace") for row in listing.stdout.split(b"\0") if row}


def _links_to_tracked_file(repo: Path, link: str, tracked: set[str]) -> bool:
    """True when ``link`` is a relative link whose target is a tracked regular file inside ``repo``.

    An absolute target, a target outside the repository, and a dangling, untracked or directory target all fail:
    each is a link a fresh checkout cannot rebuild.
    """
    link_path = repo / link
    if Path(os.readlink(link_path)).is_absolute():
        return False
    target = link_path.resolve()
    try:
        inside = target.relative_to(repo.resolve()).as_posix()
    except ValueError:
        return False
    return inside in tracked


def test_the_tree_tracks_no_unlisted_symlinks() -> None:
    # A link target is a path on the machine that committed it. Tracked, it breaks fresh checkouts (a
    # committed `.venv` link makes `uv sync` stop with "File exists") and Windows or archive-based builds.
    # The usual cause is a link a worktree uses to share a virtualenv or node_modules, picked up by `git add -A`.
    assert [link for link in _tracked_symlinks(_REPO_ROOT) if link not in _ALLOWED_LINKS] == []


def test_every_listed_link_is_still_tracked_and_points_at_a_tracked_file() -> None:
    tracked_links = set(_tracked_symlinks(_REPO_ROOT))
    assert sorted(_ALLOWED_LINKS - tracked_links) == [], "a listed link that is no longer tracked must leave the list"
    tracked = _tracked_paths(_REPO_ROOT)
    assert [link for link in sorted(_ALLOWED_LINKS) if not _links_to_tracked_file(_REPO_ROOT, link, tracked)] == []


@pytest.mark.skipif(sys.platform == "win32", reason=_NO_SYMLINK_SUPPORT)
def test_detector_reports_a_staged_symlink_and_not_a_regular_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "plain.txt").write_text("content\n", encoding="utf-8")
    (tmp_path / "linked").symlink_to("/nonexistent/target")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert _tracked_symlinks(tmp_path) == ["linked"]


@pytest.mark.skipif(sys.platform == "win32", reason=_NO_SYMLINK_SUPPORT)
@pytest.mark.parametrize(
    ("target", "accepted"),
    [
        ("plain.txt", True),
        ("<absolute path of plain.txt>", False),
        ("../outside.txt", False),
        ("missing.txt", False),
        ("untracked.txt", False),
        ("folder", False),
    ],
)
def test_link_check_accepts_only_a_relative_link_to_a_tracked_file(tmp_path: Path, target: str, accepted: bool) -> None:
    repo = tmp_path / "repo"
    (repo / "folder").mkdir(parents=True)
    for name in ("plain.txt", "untracked.txt"):
        (repo / name).write_text("content\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("content\n", encoding="utf-8")
    link_target = str(repo / "plain.txt") if target.startswith("<absolute") else target
    (repo / "linked").symlink_to(link_target)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "plain.txt", "linked"], cwd=repo, check=True)
    assert _links_to_tracked_file(repo, "linked", _tracked_paths(repo)) is accepted
