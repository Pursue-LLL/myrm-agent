"""Hardened git argv: a repository's own config can no longer pick a program that runs during a read.

[INPUT]
- core.security.safe_git (POS: hardened argv for the application's automatic git reads)

[OUTPUT]
- Real ``git`` runs against repositories whose config names marker-writing programs: each program vector fires on
  the plain command and stays silent on the hardened one, while user-owned config keeps working.

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

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No system config, and an empty global file the tests may fill in."""
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    return global_config


@pytest.fixture
def markers(tmp_path: Path) -> Path:
    directory = tmp_path / "markers"
    directory.mkdir()
    return directory


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "a@example.com")
    _git(workspace, "config", "user.name", "a")
    (workspace / "f.txt").write_text("one\n")
    _git(workspace, "add", "f.txt")
    _git(workspace, "commit", "-q", "-m", "init")
    (workspace / "f.txt").write_text("one\ntwo\n")
    return workspace


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _program(markers: Path, name: str, *, passthrough: str = "") -> str:
    """A script that records that it ran, then passes its input through (``cat`` or ``cat "$1"``)."""
    script = markers.parent / f"{name}.sh"
    script.write_text(f"#!/bin/sh\ntouch '{markers}/{name}'\n{passthrough}\n")
    script.chmod(0o755)
    return str(script)


def _fired(markers: Path) -> set[str]:
    return {entry.name for entry in markers.iterdir()}


def _clear(markers: Path) -> None:
    for entry in markers.iterdir():
        entry.unlink()


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, check=False)


def _plain(repo: Path, *args: str) -> list[str]:
    return ["git", "-C", str(repo), *args]


def _assert_vector(repo: Path, markers: Path, name: str, *args: str) -> None:
    """The plain command fires *name*; the hardened one does not and still succeeds."""
    _run(_plain(repo, *args), repo)
    if name not in _fired(markers):
        pytest.skip(f"this git build does not run {name} for `git {' '.join(args)}`")
    _clear(markers)

    hardened = _run(hardened_git_argv(args, repo_dir=repo), repo)
    assert _fired(markers) == set(), f"{name} still ran on the hardened command"
    assert hardened.returncode in (0, 1), hardened.stderr


class TestRepositoryProgramsAreNeutralised:
    def test_fsmonitor_program(self, repo: Path, markers: Path) -> None:
        _git(repo, "status", "--porcelain")  # an index must exist before git consults the monitor
        _git(repo, "config", "core.fsmonitor", _program(markers, "fsmonitor"))
        _assert_vector(repo, markers, "fsmonitor", "status", "--porcelain")

    def test_external_diff_program(self, repo: Path, markers: Path) -> None:
        _git(repo, "config", "diff.external", _program(markers, "external"))
        _assert_vector(repo, markers, "external", "diff")

    def test_textconv_program(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt diff=evil\n")
        _git(repo, "config", "diff.evil.textconv", _program(markers, "textconv", passthrough='cat "$1"'))
        _assert_vector(repo, markers, "textconv", "diff")

    def test_diff_driver_command(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt diff=evil\n")
        _git(repo, "config", "diff.evil.command", _program(markers, "drivercmd"))
        _assert_vector(repo, markers, "drivercmd", "diff")

    def test_clean_filter(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        _git(repo, "config", "filter.evil.clean", _program(markers, "clean", passthrough="cat"))
        _assert_vector(repo, markers, "clean", "diff")

    def test_process_filter(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        _git(repo, "config", "filter.evil.process", _program(markers, "process"))
        _assert_vector(repo, markers, "process", "diff")

    def test_required_filter_does_not_make_the_read_fail(self, repo: Path, markers: Path) -> None:
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        _git(repo, "config", "filter.evil.clean", _program(markers, "clean", passthrough="cat"))
        _git(repo, "config", "filter.evil.required", "true")

        result = _run(hardened_git_argv(("diff",), repo_dir=repo), repo)

        assert result.returncode == 0, result.stderr
        assert _fired(markers) == set()

    @pytest.mark.parametrize("subcommand", ["log", "show"])
    def test_textconv_does_not_run_while_showing_history(self, repo: Path, markers: Path, subcommand: str) -> None:
        (repo / ".gitattributes").write_text("*.txt diff=evil\n")
        _git(repo, "add", ".gitattributes", "f.txt")
        _git(repo, "commit", "-q", "-m", "change f.txt under the driver")
        _git(repo, "config", "diff.evil.textconv", _program(markers, "textconv", passthrough='cat "$1"'))
        args = ("log", "-p", "-1") if subcommand == "log" else ("show", "HEAD")
        _assert_vector(repo, markers, "textconv", *args)

    def test_submodule_configuration_is_not_consulted_by_status_or_diff(
        self, repo: Path, markers: Path, tmp_path: Path
    ) -> None:
        """git runs a child ``status`` inside a submodule, which reads that submodule's own stored config."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        _git(upstream, "init", "-q")
        _git(upstream, "config", "user.email", "a@example.com")
        _git(upstream, "config", "user.name", "a")
        (upstream / "s.txt").write_text("a\n")
        _git(upstream, "add", "s.txt")
        _git(upstream, "commit", "-q", "-m", "s")
        _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(upstream), "sm")
        _git(repo, "commit", "-q", "-m", "sm")
        (repo / "sm" / ".gitattributes").write_text("*.txt filter=evil\n")
        module_config = repo / ".git" / "modules" / "sm" / "config"
        _git(
            repo, "config", "-f", str(module_config), "filter.evil.clean", _program(markers, "clean", passthrough="cat")
        )
        (repo / "sm" / "s.txt").write_text("b\n")  # same size as before, so git must compare content

        for args in (("status", "--porcelain"), ("diff",)):
            _clear(markers)
            _run(_plain(repo, *args), repo)
            if "clean" not in _fired(markers):
                pytest.skip(f"this git build does not inspect submodules for `git {args[0]}`")
            _clear(markers)

            hardened = _run(hardened_git_argv(args, repo_dir=repo), repo)

            assert _fired(markers) == set(), f"submodule filter ran for `git {args[0]}`"
            assert hardened.returncode in (0, 1), hardened.stderr

    def test_hooks_do_not_run(self, repo: Path, markers: Path) -> None:
        hook = repo / ".git" / "hooks" / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook'\n")
        hook.chmod(0o755)
        assert _run(_plain(repo, "checkout", "-q", "-b", "plain"), repo).returncode == 0
        if "hook" not in _fired(markers):
            pytest.skip("this git build does not run post-checkout here")
        _clear(markers)

        assert _run(hardened_git_argv(("checkout", "-q", "-b", "hardened"), repo_dir=repo), repo).returncode == 0
        assert _fired(markers) == set()


class TestUserOwnedConfigKeepsWorking:
    def test_global_filter_still_runs(self, repo: Path, markers: Path, _isolated_user_config: Path) -> None:
        """Only the repository's own scopes are blanked, so a user's globally installed filter stays active."""
        (repo / ".gitattributes").write_text("*.txt filter=mine\n")
        clean = _program(markers, "mine", passthrough="cat")
        _isolated_user_config.write_text(f'[filter "mine"]\n\tclean = {clean}\n')

        result = _run(hardened_git_argv(("diff",), repo_dir=repo), repo)

        assert result.returncode == 0, result.stderr
        assert _fired(markers) == {"mine"}

    def test_output_is_unchanged_for_a_plain_repository(self, repo: Path) -> None:
        plain = _run(_plain(repo, "diff", "--stat"), repo)
        hardened = _run(hardened_git_argv(("diff", "--stat"), repo_dir=repo), repo)

        assert hardened.returncode == plain.returncode == 0
        assert hardened.stdout == plain.stdout


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
        _git(repo, "config", "filter.a=b.clean", "true")

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
        _git(repo, "config", "filter.evil.clean", "true")

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
