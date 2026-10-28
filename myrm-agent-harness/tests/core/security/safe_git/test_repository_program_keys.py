"""Hardened git argv for the keys a repository uses to hide a program: fixed keys, named drivers, conditional includes.

[INPUT]
- core.security.safe_git (POS: hardened argv and the no-prompt environment for commands that write the tree)

[OUTPUT]
- Fixed credential, ask-pass, ssh, custom-transfer and submodule keys that a caller cannot override.
- ``lfs.extension`` / ``lfs.customtransfer`` programs listed and blanked like filters; a repository-local ``includeIf``
  refused; the commands ``git lfs install`` writes left alone, any other ``filter.lfs`` command blanked.
- Real ``git`` runs: a filter pulled in by an ``includeIf`` and a submodule's own smudge filter each fire on the plain
  command and never on the hardened one.

[POS]
Enforcement tests for the keys of ``hardened_git_argv`` that need no ``git-lfs`` (``test_git_lfs_programs.py`` covers
the rest) — every real-git vector first fires on the plain command, so a green hardened run cannot be vacuous.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.safe_git import (
    HARDENED_GIT_CONFIG,
    HARDENED_GIT_ENV,
    GitHardeningError,
    hardened_git_argv,
)
from tests.support.git_probe import clear, fired, git, plain, program, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)

_NEW_FIXED_KEYS = (
    "credential.helper=",
    "core.askPass=",
    "core.sshCommand=false",
    "lfs.standalonetransferagent=",
    "submodule.recurse=false",
)


@pytest.fixture(autouse=True)
def _isolated_user_config(isolated_git_config: Path) -> Path:
    return isolated_git_config


def _as_argv(repo: Path, *args: str) -> list[str]:
    return hardened_git_argv(args or ("status",), repo_dir=repo)


class TestFixedKeys:
    @pytest.mark.parametrize("item", _NEW_FIXED_KEYS)
    def test_the_key_is_set_ahead_of_the_command_and_a_caller_cannot_undo_it(self, repo: Path, item: str) -> None:
        assert item in HARDENED_GIT_CONFIG
        argv = _as_argv(repo)
        assert argv[argv.index(item) - 1] == "-c"
        key = item.partition("=")[0]
        with pytest.raises(ValueError, match="key=value"):
            hardened_git_argv(("status",), repo_dir=repo, config=(f"{key}=anything",))

    def test_the_environment_turns_terminal_prompts_off_and_cannot_be_edited(self) -> None:
        assert HARDENED_GIT_ENV == {"GIT_TERMINAL_PROMPT": "0"}
        with pytest.raises(TypeError):
            HARDENED_GIT_ENV["GIT_TERMINAL_PROMPT"] = "1"  # type: ignore[index]


class TestProgramsTheRepositoryNames:
    def test_lfs_extension_and_custom_transfer_programs_are_blanked(self, repo: Path) -> None:
        git(repo, "config", "lfs.extension.evil.clean", "evil %f")
        git(repo, "config", "lfs.extension.evil.smudge", "evil %f")
        git(repo, "config", "lfs.extension.evil.priority", "0")
        git(repo, "config", "lfs.customtransfer.evil.path", "/tmp/evil")
        git(repo, "config", "lfs.customtransfer.evil.args", "--keep")

        argv = _as_argv(repo, "add", "f.txt")

        for key in ("lfs.extension.evil.clean=", "lfs.extension.evil.smudge=", "lfs.customtransfer.evil.path="):
            assert key in argv
        assert "lfs.extension.evil.priority=" not in argv, "only the keys that name a program are blanked"
        assert "lfs.customtransfer.evil.args=" not in argv

    def test_an_included_file_is_listed_like_the_config_that_includes_it(self, repo: Path) -> None:
        (repo / ".git" / "inc.cfg").write_text('[filter "evil"]\n\tclean = evil\n')
        git(repo, "config", "include.path", "inc.cfg")

        assert "filter.evil.clean=" in _as_argv(repo, "diff")

    @pytest.mark.parametrize("condition", ["onbranch:hostile", "gitdir:/tmp/", "hasconfig:remote.*.url:*"])
    def test_a_conditional_include_in_the_repository_is_refused(self, repo: Path, condition: str) -> None:
        git(repo, "config", f"includeIf.{condition}.path", "inc.cfg")

        with pytest.raises(GitHardeningError, match="conditional include"):
            _as_argv(repo, "worktree", "add", "-B", "hostile", "../wt")

    def test_a_conditional_include_in_the_users_own_config_is_not_refused(
        self, repo: Path, _isolated_user_config: Path
    ) -> None:
        _isolated_user_config.write_text('[includeIf "gitdir:~/work/"]\n\tpath = work.cfg\n')

        assert _as_argv(repo, "status")[0] == "git"

    def test_a_conditional_include_hides_a_program_from_the_listing(
        self, repo: Path, markers: Path, tmp_path: Path
    ) -> None:
        """The listing runs on the current branch; the command's own git evaluates the condition on the new one."""
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        git(repo, "add", ".gitattributes")
        git(repo, "commit", "-q", "-m", "attributes")
        (repo / ".git" / "inc.cfg").write_text(
            f'[filter "evil"]\n\tsmudge = {program(markers, "smudge", passthrough="cat")}\n'
        )
        git(repo, "config", "includeIf.onbranch:hostile.path", "inc.cfg")
        control = tmp_path / "control"
        shutil.copytree(repo, control, symlinks=True)
        run(plain(control, "worktree", "add", "-B", "hostile", str(tmp_path / "control-wt")), control)
        if "smudge" not in fired(markers):
            pytest.skip("this git build does not evaluate onbranch includes for `git worktree add -B`")

        with pytest.raises(GitHardeningError):
            _as_argv(repo, "worktree", "add", "-B", "hostile", str(tmp_path / "wt"))


_GIT_LFS_INSTALL = {
    "filter.lfs.clean": "git-lfs clean -- %f",
    "filter.lfs.smudge": "git-lfs smudge -- %f",
    "filter.lfs.process": "git-lfs filter-process",
}


class TestTheCommandsGitLfsInstallWrites:
    def test_a_repository_local_install_is_left_active(self, repo: Path) -> None:
        for key, value in _GIT_LFS_INSTALL.items():
            git(repo, "config", key, value)
        git(repo, "config", "filter.lfs.required", "true")

        argv = _as_argv(repo, "worktree", "add", "-B", "task", "../wt")

        assert not [item for item in argv if item.startswith("filter.lfs.")]

    def test_the_skip_smudge_install_is_left_active_too(self, repo: Path) -> None:
        git(repo, "config", "filter.lfs.clean", _GIT_LFS_INSTALL["filter.lfs.clean"])
        git(repo, "config", "filter.lfs.smudge", "git-lfs smudge --skip -- %f")
        git(repo, "config", "filter.lfs.process", "git-lfs filter-process --skip")

        assert not [item for item in _as_argv(repo, "add", "f.txt") if item.startswith("filter.lfs.")]

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("filter.lfs.smudge", "git-lfs smudge -- %f; touch /tmp/evil"),
            ("filter.lfs.clean", "/tmp/evil clean -- %f"),
            ("filter.lfs.process", "git-lfs filter-process --anything"),
            ("filter.lfs.clean", "git-lfs clean -- %f "),
        ],
    )
    def test_any_other_command_under_the_same_name_is_blanked(self, repo: Path, key: str, value: str) -> None:
        for name, standard in _GIT_LFS_INSTALL.items():
            git(repo, "config", name, standard)
        git(repo, "config", key, value)

        argv = _as_argv(repo, "add", "f.txt")

        assert f"{key}=" in argv
        assert [item for item in argv if item.startswith("filter.lfs.") and item.endswith("=")] == [f"{key}="]

    def test_one_non_standard_occurrence_of_a_key_is_enough(self, repo: Path) -> None:
        git(repo, "config", "--add", "filter.lfs.clean", _GIT_LFS_INSTALL["filter.lfs.clean"])
        git(repo, "config", "--add", "filter.lfs.clean", "/tmp/evil")

        assert "filter.lfs.clean=" in _as_argv(repo, "add", "f.txt")

    def test_a_blanked_command_of_a_required_filter_is_not_waved_through_by_a_standard_one(self, repo: Path) -> None:
        git(repo, "config", "filter.lfs.required", "true")
        git(repo, "config", "filter.lfs.clean", "/tmp/evil")
        git(repo, "config", "filter.lfs.smudge", _GIT_LFS_INSTALL["filter.lfs.smudge"])

        assert "filter.lfs.required=false" not in _as_argv(repo, "add", "f.txt")
        assert "filter.lfs.required=false" in _as_argv(repo, "status")


class TestSubmodulesAreNotUpdatedRecursively:
    @pytest.fixture
    def parent(self, repo: Path, markers: Path, tmp_path: Path) -> Path:
        """A repository whose submodule has its own smudge filter and whose branch ``moved`` points it at a new commit."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        git(upstream, "init", "-q")
        git(upstream, "config", "user.email", "a@example.com")
        git(upstream, "config", "user.name", "a")
        (upstream / ".gitattributes").write_text("*.txt filter=evil\n")
        (upstream / "s.txt").write_text("v1\n")
        git(upstream, "add", ".gitattributes", "s.txt")
        git(upstream, "commit", "-q", "-m", "v1")
        git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(upstream), "sm")
        git(repo, "commit", "-q", "-am", "add submodule")
        (upstream / "s.txt").write_text("v2\n")
        git(upstream, "commit", "-q", "-am", "v2")
        branch = run(plain(repo, "branch", "--show-current"), repo).stdout.decode().strip()
        git(repo, "checkout", "-q", "-b", "moved")
        git(repo / "sm", "fetch", "-q")
        git(repo / "sm", "checkout", "-q", "FETCH_HEAD")
        git(repo, "commit", "-q", "-am", "move submodule")
        git(repo, "checkout", "-q", branch)
        git(repo / "sm", "checkout", "-q", "HEAD@{1}")
        smudge = program(markers, "smudge", passthrough="cat")
        git(repo, "config", "-f", str(repo / ".git" / "modules" / "sm" / "config"), "filter.evil.smudge", smudge)
        git(repo, "config", "submodule.recurse", "true")
        return repo

    def test_a_checkout_does_not_run_the_submodules_own_filter(
        self, parent: Path, markers: Path, tmp_path: Path
    ) -> None:
        control = tmp_path / "control"
        shutil.copytree(parent, control, symlinks=True)
        git(
            control / "sm", "update-index", "-q", "--refresh"
        )  # a copy has new inode data; read-tree needs a fresh index
        outcome = run(plain(control, "checkout", "moved"), control)
        if "smudge" not in fired(markers):
            pytest.skip(
                f"this git build does not update a submodule's files while switching branches: {outcome.stderr!r}"
            )
        clear(markers)

        result = run(hardened_git_argv(("checkout", "moved"), repo_dir=parent), parent)

        assert fired(markers) == set()
        assert result.returncode == 0, result.stderr
