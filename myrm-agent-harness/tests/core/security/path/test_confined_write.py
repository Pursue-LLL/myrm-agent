"""Tests for the confined write primitive: new files below a trusted directory that no link can redirect.

[INPUT]
- core.security.path::open_directory_beneath, ConfinedDirectory, UnsafeDirectoryError (POS: the primitive under test,
  imported through the package facade)

[OUTPUT]
- Fails when a symlink or hard link, planted before the write or swapped in during it, lets a write land outside the
  directory it was made for, or when the primitive refuses a plain directory or creates a file that is not new.

[POS]
Unit contract of the primitive the download storage saves through. Each attack runs against real links and records what
happened to a victim file outside the trusted root; the checks that do not depend on a descriptor-anchored directory run
a second time on the ``lstat`` fallback (Windows), which is what ``os.supports_dir_fd`` being empty selects.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.path import (
    ConfinedDirectory,
    UnsafeDirectoryError,
    open_directory_beneath,
)

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="creating links needs privileges on Windows")
_ORIGINAL = b"outside, must stay as it is"


@pytest.fixture(params=("descriptors", "lstat"))
def anchoring(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test with directories anchored on descriptors, then again on the ``lstat`` fallback."""
    if request.param == "lstat":
        monkeypatch.setattr(os, "supports_dir_fd", set())
    return str(request.param)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    workspace = tmp_path.resolve() / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def victim(tmp_path: Path) -> Path:
    """A file outside the trusted root that no write of the primitive may reach."""
    outside = tmp_path.resolve() / "outside"
    outside.mkdir()
    file = outside / "victim.txt"
    file.write_bytes(_ORIGINAL)
    return file


def _write(fd: int, data: bytes) -> None:
    with os.fdopen(fd, "wb") as target:
        target.write(data)


def _downloads(root: Path) -> ConfinedDirectory:
    return open_directory_beneath(root, (".agent", "downloads"))


@pytest.mark.usefixtures("anchoring")
class TestDirectories:
    def test_missing_directories_are_created_below_the_root(self, root: Path) -> None:
        with _downloads(root) as directory:
            assert directory.path == root / ".agent" / "downloads"

        assert (root / ".agent" / "downloads").is_dir()

    def test_an_existing_directory_is_reused(self, root: Path) -> None:
        (root / ".agent" / "downloads").mkdir(parents=True)
        (root / ".agent" / "downloads" / "kept.pdf").write_bytes(b"x")

        with _downloads(root) as directory, directory.scandir() as entries:
            assert [entry.name for entry in entries] == ["kept.pdf"]

    def test_nothing_is_created_when_creating_is_not_asked_for(self, root: Path) -> None:
        with pytest.raises(FileNotFoundError):
            open_directory_beneath(root, (".agent", "downloads"), create=False)

        assert not (root / ".agent").exists()

    @POSIX_ONLY
    def test_the_root_itself_may_be_a_link(self, root: Path, tmp_path: Path) -> None:
        """The root is what the caller trusts and resolved, so only the names below it are checked."""
        alias = tmp_path / "alias"
        alias.symlink_to(root)

        with open_directory_beneath(alias, ("downloads",)) as directory:
            assert directory.path == alias / "downloads"

        assert (root / "downloads").is_dir()

    def test_a_file_in_the_way_is_not_a_directory(self, root: Path) -> None:
        (root / ".agent").write_text("x", encoding="utf-8")

        with pytest.raises(NotADirectoryError):
            _downloads(root)

    @pytest.mark.parametrize("parts", [("..",), (".",), ("",), ("a/b",), (".agent", "../..")])
    def test_names_that_are_not_one_segment_are_refused(self, root: Path, parts: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="single path segment"):
            open_directory_beneath(root, parts)

    def test_the_root_must_be_absolute(self) -> None:
        with pytest.raises(ValueError, match="absolute"):
            open_directory_beneath(Path("relative"), ("downloads",))


@POSIX_ONLY
@pytest.mark.usefixtures("anchoring")
class TestLinksInThePath:
    @pytest.mark.parametrize("linked", [".agent", "downloads"])
    def test_a_link_to_a_directory_outside_the_root_is_refused(self, root: Path, victim: Path, linked: str) -> None:
        link = root / ".agent" if linked == ".agent" else root / ".agent" / "downloads"
        link.parent.mkdir(exist_ok=True)
        link.symlink_to(victim.parent)

        with pytest.raises(UnsafeDirectoryError) as refused:
            _downloads(root)

        assert refused.value.component == linked
        assert sorted(entry.name for entry in victim.parent.iterdir()) == ["victim.txt"]

    def test_a_link_to_a_directory_inside_the_root_is_refused_too(self, root: Path) -> None:
        """Where it points is not the point: a link to ``.git/hooks`` is inside the workspace and still must not be written."""
        hooks = root / ".git" / "hooks"
        hooks.mkdir(parents=True)
        (root / ".agent").mkdir()
        (root / ".agent" / "downloads").symlink_to(hooks)

        with pytest.raises(UnsafeDirectoryError):
            _downloads(root)

        assert list(hooks.iterdir()) == []

    def test_a_dangling_link_is_refused_and_not_created_through(self, root: Path, tmp_path: Path) -> None:
        (root / ".agent").mkdir()
        missing = tmp_path / "does-not-exist"
        (root / ".agent" / "downloads").symlink_to(missing)

        with pytest.raises(UnsafeDirectoryError):
            _downloads(root)

        assert not missing.exists()


@POSIX_ONLY
@pytest.mark.usefixtures("anchoring")
class TestCreatingFiles:
    def test_a_file_is_created_exclusively_and_written_through_its_descriptor(self, root: Path) -> None:
        with _downloads(root) as directory:
            _write(directory.create_new("a.pdf"), b"body")

            with pytest.raises(FileExistsError):
                directory.create_new("a.pdf")

        assert (root / ".agent" / "downloads" / "a.pdf").read_bytes() == b"body"

    def test_a_link_planted_under_the_wanted_name_is_not_followed(self, root: Path, victim: Path) -> None:
        with _downloads(root) as directory:
            (directory.path / "a.pdf").symlink_to(victim)

            with pytest.raises(FileExistsError):
                directory.create_new("a.pdf")

        assert victim.read_bytes() == _ORIGINAL

    def test_a_hard_link_planted_under_the_wanted_name_is_not_opened(self, root: Path, victim: Path) -> None:
        with _downloads(root) as directory:
            os.link(victim, directory.path / "a.pdf")

            with pytest.raises(FileExistsError):
                directory.create_new("a.pdf")

        assert victim.read_bytes() == _ORIGINAL

    def test_a_link_swapped_in_after_the_file_was_created_does_not_redirect_the_write(
        self, root: Path, victim: Path
    ) -> None:
        with _downloads(root) as directory:
            fd = directory.create_new("a.pdf")
            (directory.path / "a.pdf").unlink()
            (directory.path / "a.pdf").symlink_to(victim)

            _write(fd, b"attacker-visible download")

        assert victim.read_bytes() == _ORIGINAL

    def test_a_hard_link_swapped_in_after_the_file_was_created_does_not_redirect_the_write(
        self, root: Path, victim: Path
    ) -> None:
        with _downloads(root) as directory:
            fd = directory.create_new("a.pdf")
            (directory.path / "a.pdf").unlink()
            os.link(victim, directory.path / "a.pdf")

            _write(fd, b"attacker-visible download")

        assert victim.read_bytes() == _ORIGINAL

    def test_unlinking_a_name_removes_a_link_and_not_what_it_points_to(self, root: Path, victim: Path) -> None:
        with _downloads(root) as directory:
            (directory.path / "a.pdf").symlink_to(victim)

            directory.unlink("a.pdf")

            assert not (directory.path / "a.pdf").is_symlink()

        assert victim.read_bytes() == _ORIGINAL

    @pytest.mark.parametrize("name", ["", ".", "..", "../escape.pdf", "sub/escape.pdf"])
    def test_a_name_that_is_not_one_segment_is_refused(self, root: Path, name: str) -> None:
        with _downloads(root) as directory:
            with pytest.raises(ValueError, match="single path segment"):
                directory.create_new(name)
            with pytest.raises(ValueError, match="single path segment"):
                directory.unlink(name)

        assert not (root / ".agent" / "escape.pdf").exists()

    def test_the_directory_can_be_listed_again_and_again(self, root: Path) -> None:
        with _downloads(root) as directory:
            _write(directory.create_new("a.pdf"), b"x")

            for _ in range(3):
                with directory.scandir() as entries:
                    assert [entry.name for entry in entries] == ["a.pdf"]

    def test_a_listing_that_is_still_open_does_not_cut_the_next_one_short(self, root: Path) -> None:
        with _downloads(root) as directory:
            for name in ("a.pdf", "b.pdf", "c.pdf"):
                _write(directory.create_new(name), b"x")

            with directory.scandir() as first:
                next(first)
                with directory.scandir() as second:
                    assert sorted(entry.name for entry in second) == ["a.pdf", "b.pdf", "c.pdf"]

    def test_a_file_created_after_a_listing_is_in_the_next_one(self, root: Path) -> None:
        with _downloads(root) as directory:
            _write(directory.create_new("a.pdf"), b"x")
            with directory.scandir() as entries:
                assert [entry.name for entry in entries] == ["a.pdf"]

            _write(directory.create_new("b.pdf"), b"x")

            with directory.scandir() as entries:
                assert sorted(entry.name for entry in entries) == ["a.pdf", "b.pdf"]

    def test_the_entries_of_an_open_listing_can_be_inspected(self, root: Path) -> None:
        with _downloads(root) as directory:
            _write(directory.create_new("a.pdf"), b"12345")

            with directory.scandir() as entries:
                (entry,) = entries
                assert entry.is_file(follow_symlinks=False)
                assert entry.stat(follow_symlinks=False).st_size == 5


@POSIX_ONLY
class TestAnchoring:
    def test_a_directory_replaced_after_it_was_opened_keeps_the_files_it_was_opened_for(
        self, root: Path, victim: Path
    ) -> None:
        """The descriptor, not the name, is what the later creates are resolved against."""
        with _downloads(root) as directory:
            (root / ".agent" / "downloads").rename(root / ".agent" / "moved")
            (root / ".agent" / "downloads").symlink_to(victim.parent)

            _write(directory.create_new("a.pdf"), b"body")

        assert (root / ".agent" / "moved" / "a.pdf").read_bytes() == b"body"
        assert sorted(entry.name for entry in victim.parent.iterdir()) == ["victim.txt"]


@pytest.mark.usefixtures("anchoring")
class TestAClosedDirectory:
    """Closing releases the descriptor; a closed directory refuses every use instead of falling back to the path."""

    def test_every_use_is_refused(self, root: Path) -> None:
        directory = _downloads(root)
        directory.close()

        with pytest.raises(ValueError, match="closed"):
            directory.create_new("a.pdf")
        with pytest.raises(ValueError, match="closed"):
            directory.unlink("a.pdf")
        with pytest.raises(ValueError, match="closed"), directory.scandir():
            pass

    @POSIX_ONLY
    def test_a_link_standing_where_the_directory_was_is_not_followed_after_closing(
        self, root: Path, victim: Path
    ) -> None:
        directory = _downloads(root)
        directory.close()
        downloads = root / ".agent" / "downloads"
        downloads.rmdir()
        downloads.symlink_to(victim.parent)

        with pytest.raises(ValueError, match="closed"):
            directory.create_new("planted.txt")

        assert sorted(entry.name for entry in victim.parent.iterdir()) == ["victim.txt"]

    def test_closing_again_does_nothing(self, root: Path) -> None:
        directory = _downloads(root)

        directory.close()
        directory.close()
