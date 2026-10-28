"""Hardened git argv: a repository's own config cannot pick a program that runs during an application git command.

[INPUT]
- core.security.safe_git (POS: hardened argv for the application's automatic git commands)

[OUTPUT]
- Real ``git`` runs against repositories whose config names marker-writing programs: each program vector fires on
  the plain command and stays silent on the hardened one — including a bare repository nested in a working tree
  and entered directly — while user-owned config keeps working.

[POS]
Enforcement tests for ``hardened_git_argv`` — the control run proves the vector is live on this git build, so a
green hardened run cannot be vacuous.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.safe_git import (
    HARDENED_GIT_CONFIG,
    GitHardeningError,
    hardened_git_argv,
    hardened_git_argv_async,
)
from tests.support.git_probe import clear, fired, git, plain, program, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)


@pytest.fixture(autouse=True)
def _isolated_user_config(isolated_git_config: Path) -> Path:
    return isolated_git_config


def _assert_vector(repo: Path, markers: Path, name: str, *args: str) -> None:
    """The plain command fires *name*; the hardened one does not and still succeeds."""
    run(plain(repo, *args), repo)
    if name not in fired(markers):
        pytest.skip(f"this git build does not run {name} for `git {' '.join(args)}`")
    clear(markers)

    hardened = run(hardened_git_argv(args, repo_dir=repo), repo)
    assert fired(markers) == set(), f"{name} still ran on the hardened command"
    assert hardened.returncode in (0, 1), hardened.stderr


class TestRepositoryProgramsAreNeutralised:
    def test_fsmonitor_program(self, repo: Path, markers: Path) -> None:
        git(repo, "status", "--porcelain")  # an index must exist before git consults the monitor
        git(repo, "config", "core.fsmonitor", program(markers, "fsmonitor"))
        _assert_vector(repo, markers, "fsmonitor", "status", "--porcelain")

    def test_external_diff_program(self, repo: Path, markers: Path) -> None:
        git(repo, "config", "diff.external", program(markers, "external"))
        _assert_vector(repo, markers, "external", "diff")

    def test_textconv_program(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt diff=evil\n")
        git(repo, "config", "diff.evil.textconv", program(markers, "textconv", passthrough='cat "$1"'))
        _assert_vector(repo, markers, "textconv", "diff")

    def test_diff_driver_command(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt diff=evil\n")
        git(repo, "config", "diff.evil.command", program(markers, "drivercmd"))
        _assert_vector(repo, markers, "drivercmd", "diff")

    def test_clean_filter(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        git(repo, "config", "filter.evil.clean", program(markers, "clean", passthrough="cat"))
        _assert_vector(repo, markers, "clean", "diff")

    def test_process_filter(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        git(repo, "config", "filter.evil.process", program(markers, "process"))
        _assert_vector(repo, markers, "process", "diff")

    def test_required_filter_does_not_make_the_read_fail(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        git(repo, "config", "filter.evil.clean", program(markers, "clean", passthrough="cat"))
        git(repo, "config", "filter.evil.required", "true")

        result = run(hardened_git_argv(("diff",), repo_dir=repo), repo)

        assert result.returncode == 0, result.stderr
        assert fired(markers) == set()

    @pytest.mark.parametrize("subcommand", ["log", "show"])
    def test_textconv_does_not_run_while_showing_history(self, repo: Path, markers: Path, subcommand: str) -> None:
        (repo / ".gitattributes").write_text("*.txt diff=evil\n")
        git(repo, "add", ".gitattributes", "f.txt")
        git(repo, "commit", "-q", "-m", "change f.txt under the driver")
        git(repo, "config", "diff.evil.textconv", program(markers, "textconv", passthrough='cat "$1"'))
        args = ("log", "-p", "-1") if subcommand == "log" else ("show", "HEAD")
        _assert_vector(repo, markers, "textconv", *args)

    def test_submodule_configuration_is_not_consulted_by_status_or_diff(
        self, repo: Path, markers: Path, tmp_path: Path
    ) -> None:
        """git runs a child ``status`` inside a submodule, which reads that submodule's own stored config."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        git(upstream, "init", "-q")
        git(upstream, "config", "user.email", "a@example.com")
        git(upstream, "config", "user.name", "a")
        (upstream / "s.txt").write_text("a\n")
        git(upstream, "add", "s.txt")
        git(upstream, "commit", "-q", "-m", "s")
        git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(upstream), "sm")
        git(repo, "commit", "-q", "-m", "sm")
        (repo / "sm" / ".gitattributes").write_text("*.txt filter=evil\n")
        module_config = repo / ".git" / "modules" / "sm" / "config"
        git(repo, "config", "-f", str(module_config), "filter.evil.clean", program(markers, "clean", passthrough="cat"))
        (repo / "sm" / "s.txt").write_text("b\n")  # same size as before, so git must compare content

        for args in (("status", "--porcelain"), ("diff",)):
            clear(markers)
            run(plain(repo, *args), repo)
            if "clean" not in fired(markers):
                pytest.skip(f"this git build does not inspect submodules for `git {args[0]}`")
            clear(markers)

            hardened = run(hardened_git_argv(args, repo_dir=repo), repo)

            assert fired(markers) == set(), f"submodule filter ran for `git {args[0]}`"
            assert hardened.returncode in (0, 1), hardened.stderr

    @pytest.mark.parametrize("args", [("status", "--porcelain"), ("diff", "--stat")])
    def test_bare_repository_nested_in_a_working_tree(
        self, tmp_path: Path, markers: Path, args: tuple[str, ...]
    ) -> None:
        """A bare repository that names its own ``core.worktree`` is what git discovers when run from inside it."""
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "file.txt").write_text("one\n")
        nested = tmp_path / "nested.git"
        git(tmp_path, "init", "-q", "--bare", str(nested))
        git(tmp_path, f"--git-dir={nested}", f"--work-tree={vendor}", "add", "file.txt")
        git(nested, "config", "core.bare", "false")
        git(nested, "config", "core.worktree", str(vendor))
        git(nested, "config", "core.fsmonitor", program(markers, "fsmonitor"))
        (vendor / "file.txt").write_text("one\ntwo\n")

        _assert_vector(nested, markers, "fsmonitor", *args)

    def test_hooks_do_not_run(self, repo: Path, markers: Path) -> None:
        hook = repo / ".git" / "hooks" / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook'\n")
        hook.chmod(0o755)
        assert run(plain(repo, "checkout", "-q", "-b", "plain"), repo).returncode == 0
        if "hook" not in fired(markers):
            pytest.skip("this git build does not run post-checkout here")
        clear(markers)

        assert run(hardened_git_argv(("checkout", "-q", "-b", "hardened"), repo_dir=repo), repo).returncode == 0
        assert fired(markers) == set()


class TestUserOwnedConfigKeepsWorking:
    def test_global_filter_still_runs(self, repo: Path, markers: Path, _isolated_user_config: Path) -> None:
        """Only the repository's own scopes are blanked, so a user's globally installed filter stays active."""
        (repo / ".gitattributes").write_text("*.txt filter=mine\n")
        clean = program(markers, "mine", passthrough="cat")
        _isolated_user_config.write_text(f'[filter "mine"]\n\tclean = {clean}\n')

        result = run(hardened_git_argv(("diff",), repo_dir=repo), repo)

        assert result.returncode == 0, result.stderr
        assert fired(markers) == {"mine"}

    def test_output_is_unchanged_for_a_plain_repository(self, repo: Path) -> None:
        unhardened = run(plain(repo, "diff", "--stat"), repo)
        hardened = run(hardened_git_argv(("diff", "--stat"), repo_dir=repo), repo)

        assert hardened.returncode == unhardened.returncode == 0
        assert hardened.stdout == unhardened.stdout


class TestArgvShape:
    def test_base_config_precedes_the_caller_arguments(self, repo: Path) -> None:
        argv = hardened_git_argv(("status", "--porcelain"), repo_dir=repo)

        assert argv[0] == "git"
        assert argv[-1] == "--porcelain"
        assert "status" in argv[argv.index("-C") + 2 :]
        assert argv[argv.index("-C") + 1] == str(repo.resolve())
        for item in HARDENED_GIT_CONFIG:
            assert argv[argv.index(item) - 1] == "-c"

    def test_a_directory_that_is_not_a_repository_gets_the_base_config_only(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        argv = hardened_git_argv(("status",), repo_dir=plain_dir)

        assert argv.count("-c") == len(HARDENED_GIT_CONFIG)

    def test_a_driver_name_that_cannot_be_blanked_refuses_to_run(self, repo: Path) -> None:
        """``-c key=value`` splits on the first ``=``, so a name containing one could dodge the override."""
        git(repo, "config", "filter.a=b.clean", "true")

        with pytest.raises(GitHardeningError):
            hardened_git_argv(("status",), repo_dir=repo)

    @pytest.mark.parametrize(
        "args",
        [("rev-parse", "HEAD"), ("log", "-1"), ("show", "HEAD"), ("diff-tree", "-r", "HEAD"), ("ls-tree", "HEAD")],
    )
    def test_object_only_subcommands_skip_the_repository_listing(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...]
    ) -> None:
        """No working-tree file is hashed, so no filter can run; the extra git process is not worth paying for."""
        git(repo, "config", "filter.evil.clean", "true")

        def _no_query(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the repository listing ran")

        monkeypatch.setattr(subprocess, "run", _no_query)

        argv = hardened_git_argv(args, repo_dir=repo)

        assert not any(item.startswith("filter.") for item in argv)

    @pytest.mark.parametrize("args", [(), ("--version",), ("-c", "a=b", "status")])
    def test_arguments_must_start_with_a_subcommand(self, repo: Path, args: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="subcommand"):
            hardened_git_argv(args, repo_dir=repo)

    @pytest.mark.parametrize(
        ("args", "expected_flags"),
        [
            (("diff", "--stat"), ["--no-ext-diff", "--no-textconv", "--ignore-submodules=dirty"]),
            (("log", "-1"), ["--no-ext-diff", "--no-textconv"]),
            (("show", "HEAD"), ["--no-ext-diff", "--no-textconv"]),
            (("status", "--porcelain"), ["--ignore-submodules=dirty"]),
            (("ls-files", "-z"), []),
        ],
    )
    def test_subcommand_flags_sit_between_the_subcommand_and_the_caller_arguments(
        self, repo: Path, args: tuple[str, ...], expected_flags: list[str]
    ) -> None:
        argv = hardened_git_argv(args, repo_dir=repo)

        assert argv[argv.index(args[0]) :] == [args[0], *expected_flags, *args[1:]]

    async def test_async_variant_matches_the_sync_one(self, repo: Path) -> None:
        assert await hardened_git_argv_async(("status",), repo_dir=repo) == hardened_git_argv(
            ("status",), repo_dir=repo
        )


def test_hosts_reach_the_hardened_argv_through_the_api_facade() -> None:
    """The server imports ``api.security``; it must hand out the exact objects, not divergent copies."""
    from myrm_agent_harness.api import security

    assert security.hardened_git_argv is hardened_git_argv
    assert security.hardened_git_argv_async is hardened_git_argv_async
    assert security.GitHardeningError is GitHardeningError
