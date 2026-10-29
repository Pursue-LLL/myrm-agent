"""Git skill install: which files of a cloned skill are read, and what stops the read.

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.git_installer: `GitInstaller`, `_find_skill_md`, `_walk_skill_dir`
- myrm_agent_harness.agent.skills.market.sanitizer: the size limits the install step applies

[OUTPUT]
- Hidden and junk directories are judged by names below the skill directory only and are never entered
- A symlink is followed only when its real target is inside the clone; a link leaving it is skipped with a warning,
  a symlinked directory is never entered by the walk
- A link loop is skipped on its own: the other files of its directory are still read, the SKILL.md search goes on, and a
  SKILL.md that is a loop is reported as not found
- A file over the single-file limit, or a skill over the total limit, is refused before the bytes are read; files in
  filtered paths (`dist/`, `build/`) count toward neither

[POS]
myrm-agent-harness/tests/agent/skills/market/installers/test_git_installer_collection.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.market.installers.git_installer import (
    GitInstaller,
    _find_skill_md,
    _walk_skill_dir,
)
from myrm_agent_harness.agent.skills.market.sanitizer import MAX_SINGLE_FILE_SIZE, MAX_TOTAL_UPLOAD_SIZE

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"


def _link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip("symlinks are not available on this platform")


def _record_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Log the name of every file whose bytes `Path.read_bytes` reads."""
    read: list[str] = []
    original = Path.read_bytes

    def recording(self: Path) -> bytes:
        read.append(self.name)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", recording)
    return read


def _file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    root.mkdir()
    return root


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    directory = tmp_path / "outside"
    _file(directory / "SKILL.md", SKILL_MD)
    _file(directory / "secret.txt", b"outside the clone")
    return directory


class TestWalkSkillDir:
    def test_excludes_hidden_and_junk_dirs(self, tmp_path: Path) -> None:
        for rel in (".hidden/x.txt", "node_modules/y.txt", "ok.txt", ".git/z.txt", "__pycache__/w.txt"):
            _file(tmp_path / rel)

        assert {p.name for p in _walk_skill_dir(tmp_path)} == {"ok.txt"}

    def test_a_hidden_ancestor_of_the_skill_dir_does_not_count(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".cache" / "skill_git_x"
        _file(skill_dir / "SKILL.md", SKILL_MD)
        _file(skill_dir / "run.py", b"print('x')")

        assert {p.name for p in _walk_skill_dir(skill_dir)} == {"SKILL.md", "run.py"}

    def test_walk_survives_permission_error(self, tmp_path: Path) -> None:
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        _file(tmp_path / "ok.txt")
        blocked.chmod(0o000)
        try:
            names = {p.name for p in _walk_skill_dir(tmp_path)}
        finally:
            blocked.chmod(0o755)

        assert names == {"ok.txt"}

    def test_file_link_inside_the_boundary_is_followed(self, clone: Path) -> None:
        skill_dir = clone / "mirror" / "alpha"
        _file(clone / "agents" / "alpha.md", SKILL_MD)
        _link(skill_dir / "SKILL.md", clone / "agents" / "alpha.md")

        assert [p.name for p in _walk_skill_dir(skill_dir, clone)] == ["SKILL.md"]

    def test_the_boundary_defaults_to_the_skill_dir(self, clone: Path) -> None:
        skill_dir = clone / "mirror" / "alpha"
        _file(clone / "agents" / "alpha.md", SKILL_MD)
        _link(skill_dir / "SKILL.md", clone / "agents" / "alpha.md")

        assert _walk_skill_dir(skill_dir) == []

    def test_file_link_leaving_the_boundary_is_skipped_with_a_warning(
        self, clone: Path, outside: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        _link(clone / "leak.txt", outside / "secret.txt")

        with caplog.at_level(logging.WARNING):
            names = {p.name for p in _walk_skill_dir(clone, clone)}

        assert names == {"SKILL.md"}
        assert "leak.txt" in caplog.text

    def test_symlinked_directory_is_not_entered(self, clone: Path, tmp_path: Path) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        _file(clone / "elsewhere" / "inner.txt")
        _link(clone / "alias", clone / "elsewhere")

        names = {str(p.relative_to(clone)) for p in _walk_skill_dir(clone, clone)}

        assert names == {"SKILL.md", "elsewhere/inner.txt"}

    def test_a_link_loop_does_not_hide_the_other_files_of_its_directory(self, clone: Path) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        _file(clone / "notes.md")
        _link(clone / "loop.md", clone / "loop.md")
        _link(clone / "a.md", clone / "b.md")
        _link(clone / "b.md", clone / "a.md")

        names = {p.name for p in _walk_skill_dir(clone, clone)}

        assert names == {"SKILL.md", "notes.md"}


class TestFindSkillMd:
    def test_respects_depth(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "d"
        _file(deep / "SKILL.md", SKILL_MD)

        assert _find_skill_md(tmp_path) is None
        assert _find_skill_md(tmp_path, max_depth=6) == deep / "SKILL.md"

    def test_at_depth_zero(self, tmp_path: Path) -> None:
        assert _find_skill_md(tmp_path, max_depth=0) is None

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        _file(tmp_path / ".hidden" / "SKILL.md", SKILL_MD)

        assert _find_skill_md(tmp_path) is None

    def test_survives_permission_error(self, tmp_path: Path) -> None:
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        blocked.chmod(0o000)
        try:
            assert _find_skill_md(tmp_path) is None
        finally:
            blocked.chmod(0o755)

    def test_skill_md_link_leaving_the_clone_is_skipped(self, clone: Path, outside: Path) -> None:
        _link(clone / "SKILL.md", outside / "SKILL.md")

        assert _find_skill_md(clone, boundary=clone) is None

    def test_directory_link_leaving_the_clone_is_not_followed(self, clone: Path, outside: Path) -> None:
        _link(clone / "linked", outside)

        assert _find_skill_md(clone, boundary=clone) is None

    def test_directory_link_inside_the_clone_is_followed(self, clone: Path) -> None:
        scan_root = clone / "scan"
        _file(clone / "other" / "real" / "SKILL.md", SKILL_MD)
        _link(scan_root / "linked", clone / "other" / "real")

        assert _find_skill_md(scan_root, boundary=clone) == scan_root / "linked" / "SKILL.md"
        assert _find_skill_md(scan_root) is None

    def test_a_link_loop_named_like_the_skill_file_is_not_found(self, clone: Path) -> None:
        _link(clone / "SKILL.md", clone / "SKILL.md")

        assert _find_skill_md(clone, boundary=clone) is None

    def test_a_link_loop_in_a_directory_does_not_stop_the_search(self, clone: Path) -> None:
        _link(clone / "aaa" / "loop", clone / "aaa" / "loop")
        _link(clone / "SKILL.md", clone / "SKILL.md")
        _file(clone / "zzz" / "SKILL.md", SKILL_MD)

        assert _find_skill_md(clone, boundary=clone) == clone / "zzz" / "SKILL.md"


class TestCollectSkillFiles:
    def test_skill_md_that_links_to_a_file_elsewhere_in_the_clone_installs(self, clone: Path) -> None:
        skill_dir = clone / "mirror" / "alpha"
        _file(clone / "agents" / "alpha.md", SKILL_MD)
        _link(skill_dir / "SKILL.md", clone / "agents" / "alpha.md")

        result = GitInstaller()._collect_skill_files(skill_dir, clone)

        assert result.name == "Alpha"
        assert result.files == {"SKILL.md": SKILL_MD}

    def test_skill_md_that_links_out_of_the_clone_is_not_installed(self, clone: Path, outside: Path) -> None:
        skill_dir = clone / "alpha"
        _link(skill_dir / "SKILL.md", outside / "SKILL.md")

        with pytest.raises(ValueError, match=r"SKILL\.md not found"):
            GitInstaller()._collect_skill_files(skill_dir, clone)

    def test_a_skill_md_that_is_a_link_loop_is_not_installed(self, clone: Path) -> None:
        skill_dir = clone / "alpha"
        _link(skill_dir / "SKILL.md", skill_dir / "SKILL.md")

        with pytest.raises(ValueError, match=r"SKILL\.md not found"):
            GitInstaller()._collect_skill_files(skill_dir, clone)

    def test_a_link_loop_next_to_the_skill_files_does_not_empty_the_install(self, clone: Path) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        _link(clone / "loop.md", clone / "loop.md")

        assert GitInstaller()._collect_skill_files(clone).files == {"SKILL.md": SKILL_MD}

    def test_file_over_the_single_file_limit_is_refused_before_it_is_read(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        big = _file(clone / "big.bin", b"\0" * (MAX_SINGLE_FILE_SIZE + 1))
        read = _record_reads(monkeypatch)

        with pytest.raises(ValueError, match="exceeds size limit"):
            GitInstaller()._collect_skill_files(clone)

        assert big.name not in read

    def test_file_exactly_at_the_single_file_limit_is_read(self, clone: Path) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        _file(clone / "edge.bin", b"\0" * MAX_SINGLE_FILE_SIZE)

        assert len(GitInstaller()._collect_skill_files(clone).files["edge.bin"]) == MAX_SINGLE_FILE_SIZE

    def test_skill_over_the_total_limit_is_refused_before_the_last_file_is_read(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        count = MAX_TOTAL_UPLOAD_SIZE // 900_000 + 1
        for index in range(count):
            _file(clone / f"part{index}.bin", b"\0" * 900_000)
        read = _record_reads(monkeypatch)

        with pytest.raises(ValueError, match="Total upload size exceeds limit"):
            GitInstaller()._collect_skill_files(clone)

        assert len(read) < count + 1

    def test_files_in_filtered_paths_do_not_count_toward_the_limits(self, clone: Path) -> None:
        _file(clone / "SKILL.md", SKILL_MD)
        _file(clone / "dist" / "bundle.js", b"\0" * (MAX_SINGLE_FILE_SIZE + 1))
        _file(clone / "build" / "out.bin", b"\0" * MAX_TOTAL_UPLOAD_SIZE)

        assert set(GitInstaller()._collect_skill_files(clone).files) == {"SKILL.md"}
