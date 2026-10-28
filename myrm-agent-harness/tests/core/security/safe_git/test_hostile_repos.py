"""Hardened git argv for commands that update a repository or fetch for it: no program, no network, no silent rewrite.

[INPUT]
- core.security.safe_git (POS: hardened argv for the application's automatic git commands)

[OUTPUT]
- Real ``git`` runs against repositories whose config names marker-writing programs: lazy fetches from a partial
  clone, merge drivers, signing, rebase hooks and fsmonitor each fire on the plain command and stay silent on the
  hardened one; a required filter makes a write fail instead of storing raw content.

[POS]
Enforcement tests for the write side of ``hardened_git_argv`` — every vector first fires on the plain command, so a
green hardened run cannot be vacuous.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.safe_git import GitHardeningError, hardened_git_argv
from tests.support.git_probe import clear, fired, git, plain, program, run

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)


@pytest.fixture(autouse=True)
def _isolated_user_config(isolated_git_config: Path) -> Path:
    return isolated_git_config


def _commit_file(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


def _hook(repo: Path, markers: Path, name: str) -> None:
    hook = repo / ".git" / "hooks" / name
    hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook-{name}'\n")
    hook.chmod(0o755)


class TestAMissingObjectIsNeverFetched:
    """A partial clone fetches what it lacks on demand, through a program or ssh command its own config names."""

    @pytest.fixture
    def source(self, tmp_path: Path) -> Path:
        upstream = tmp_path / "source"
        upstream.mkdir()
        git(upstream, "init", "-q")
        git(upstream, "config", "user.email", "a@example.com")
        git(upstream, "config", "user.name", "a")
        git(upstream, "config", "uploadpack.allowFilter", "true")
        git(upstream, "config", "uploadpack.allowAnySHA1InWant", "true")
        _commit_file(upstream, "f.txt", "one\n", "first")
        _commit_file(upstream, "f.txt", "one\ntwo\n", "second")
        return upstream

    @staticmethod
    def _clone(source: Path, destination: Path) -> Path:
        """A partial clone whose first commit's file content was not downloaded."""
        run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "clone",
                "-q",
                "--filter=blob:none",
                f"file://{source}",
                str(destination),
            ],
            destination.parent,
        )
        return destination

    def _uploadpack_victim(self, source: Path, markers: Path, destination: Path) -> Path:
        victim = self._clone(source, destination)
        git(
            victim,
            "config",
            "remote.origin.uploadpack",
            program(markers, "uploadpack", passthrough='exec git-upload-pack "$@"'),
        )
        return victim

    def _ssh_victim(self, source: Path, markers: Path, destination: Path) -> Path:
        victim = self._clone(source, destination)
        git(victim, "config", "remote.origin.url", "ssh://example.invalid/repo.git")
        git(victim, "config", "core.sshCommand", program(markers, "ssh", passthrough="exit 1"))
        return victim

    @pytest.mark.parametrize(
        "args",
        [("show", "HEAD~1"), ("log", "-p", "-1", "HEAD~1"), ("diff", "HEAD~1", "HEAD")],
        ids=["show", "log-p", "diff"],
    )
    @pytest.mark.parametrize("route", ["uploadpack", "ssh"])
    def test_reading_history_does_not_fetch(
        self, source: Path, markers: Path, tmp_path: Path, args: tuple[str, ...], route: str
    ) -> None:
        make = self._uploadpack_victim if route == "uploadpack" else self._ssh_victim
        control = make(source, markers, tmp_path / "control")
        run(plain(control, *args), control)
        if route not in fired(markers):
            pytest.skip(f"this git build does not fetch through {route} for `git {' '.join(args)}`")
        clear(markers)

        victim = make(source, markers, tmp_path / "victim")
        hardened = run(hardened_git_argv(args, repo_dir=victim), victim)

        assert fired(markers) == set(), f"{route} still ran on the hardened command"
        assert hardened.returncode != 0, "the missing content must be an error, not a silent empty diff"

    def test_creating_a_worktree_does_not_fetch(self, source: Path, markers: Path, tmp_path: Path) -> None:
        control = self._uploadpack_victim(source, markers, tmp_path / "control")
        run(plain(control, "worktree", "add", "--detach", str(tmp_path / "control-wt"), "HEAD~1"), control)
        if "uploadpack" not in fired(markers):
            pytest.skip("this git build does not fetch while checking out a worktree")
        clear(markers)

        victim = self._uploadpack_victim(source, markers, tmp_path / "victim")
        args = ("worktree", "add", "--detach", str(tmp_path / "victim-wt"), "HEAD~1")
        hardened = run(hardened_git_argv(args, repo_dir=victim), victim)

        assert fired(markers) == set()
        assert hardened.returncode != 0


class TestMergeAndSigningRunNoProgram:
    @pytest.fixture
    def diverged(self, repo: Path) -> Path:
        """``topic`` and the current branch each add one commit to the same base; the working tree is clean."""
        git(repo, "commit", "-q", "-am", "main change")
        git(repo, "checkout", "-q", "-b", "topic", "HEAD~1")
        _commit_file(repo, "g.txt", "g\n", "topic change")
        git(repo, "checkout", "-q", "-")
        return repo

    def test_a_merge_driver_named_by_the_repository_does_not_run(self, diverged: Path, markers: Path) -> None:
        git(diverged, "checkout", "-q", "topic")
        _commit_file(diverged, "f.txt", "one\nconflicting\n", "topic edits f.txt too")
        git(diverged, "checkout", "-q", "-")
        _commit_file(diverged, ".gitattributes", "f.txt merge=evil\n", "attributes")
        git(diverged, "config", "merge.evil.driver", program(markers, "driver", passthrough="exit 0"))
        control = run(plain(diverged, "merge", "--no-ff", "-m", "m", "topic"), diverged)
        if "driver" not in fired(markers):
            pytest.skip(f"this git build does not run the merge driver here: {control.stderr!r}")
        git(diverged, "reset", "-q", "--hard", "ORIG_HEAD")
        clear(markers)

        hardened = run(hardened_git_argv(("merge", "--no-ff", "-m", "m", "topic"), repo_dir=diverged), diverged)

        assert fired(markers) == set()
        assert hardened.returncode != 0, "a blanked merge driver must stop the merge, not skip the merge step"

    @pytest.mark.parametrize(
        "args",
        [("merge", "--no-ff", "-m", "m", "topic"), ("rebase", "topic")],
        ids=["merge", "rebase"],
    )
    def test_a_signing_program_does_not_run_and_does_not_block(
        self, diverged: Path, markers: Path, args: tuple[str, ...]
    ) -> None:
        git(diverged, "config", "commit.gpgsign", "true")
        git(diverged, "config", "gpg.program", program(markers, "gpg", passthrough="exit 1"))
        control = run(plain(diverged, *args), diverged)
        if "gpg" not in fired(markers):
            pytest.skip(f"this git build does not sign during `git {args[0]}`: {control.stderr!r}")
        assert control.returncode != 0
        run(plain(diverged, args[0], "--abort"), diverged)
        git(diverged, "reset", "-q", "--hard", "HEAD")
        clear(markers)

        hardened = run(hardened_git_argv(args, repo_dir=diverged), diverged)

        assert fired(markers) == set()
        assert hardened.returncode == 0, hardened.stderr

    def test_a_commit_is_made_unsigned_when_the_repository_asks_for_signing(self, repo: Path, markers: Path) -> None:
        git(repo, "add", "f.txt")
        git(repo, "config", "commit.gpgsign", "true")
        git(repo, "config", "gpg.program", program(markers, "gpg", passthrough="exit 1"))
        control = run(plain(repo, "commit", "-m", "x"), repo)
        if "gpg" not in fired(markers):
            pytest.skip("this git build does not run the signing program for a commit")
        assert control.returncode != 0
        clear(markers)

        hardened = run(hardened_git_argv(("commit", "-m", "x"), repo_dir=repo), repo)

        assert fired(markers) == set()
        assert hardened.returncode == 0, hardened.stderr

    def test_a_merge_driver_name_that_cannot_be_blanked_refuses_to_run(self, repo: Path) -> None:
        git(repo, "config", "merge.a=b.driver", "true")

        with pytest.raises(GitHardeningError):
            hardened_git_argv(("merge", "topic"), repo_dir=repo)


class TestARequiredFilterStopsAWriteInsteadOfStoringRawContent:
    @pytest.fixture
    def pointer_filter(self, repo: Path, markers: Path) -> Path:
        """A repository-local clean filter that turns content into a pointer, the way a local LFS install does."""
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        git(repo, "config", "filter.evil.clean", program(markers, "clean", passthrough="sed 's/^/POINTER:/'"))
        git(repo, "config", "filter.evil.required", "true")
        return repo

    def test_add_fails_instead_of_staging_the_unfiltered_file(self, pointer_filter: Path, markers: Path) -> None:
        run(plain(pointer_filter, "add", "f.txt"), pointer_filter)
        if "clean" not in fired(markers):
            pytest.skip("this git build does not run the clean filter for `git add`")
        git(pointer_filter, "reset", "-q")
        clear(markers)

        hardened = run(hardened_git_argv(("add", "f.txt"), repo_dir=pointer_filter), pointer_filter)
        staged = run(plain(pointer_filter, "diff", "--cached", "--name-only"), pointer_filter)

        assert fired(markers) == set()
        assert hardened.returncode != 0
        assert staged.stdout == b"", "nothing may be staged when the repository's filter could not run"

    def test_a_private_snapshot_is_still_taken_from_the_raw_content(self, pointer_filter: Path, markers: Path) -> None:
        result = run(hardened_git_argv(("stash", "create", "snap"), repo_dir=pointer_filter), pointer_filter)

        assert fired(markers) == set()
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip(), "a dirty tree yields a snapshot commit"

    @pytest.mark.parametrize(
        ("args", "tolerates"),
        [
            (("status", "--porcelain"), True),
            (("diff",), True),
            (("ls-files",), True),
            (("stash", "create", "s"), True),
            (("add", "f.txt"), False),
            (("commit", "-m", "x"), False),
            (("rebase", "--autostash", "@{u}"), False),
            (("read-tree", "--reset", "-u", "HEAD"), True),
            (("stash", "pop"), False),
        ],
    )
    def test_only_commands_whose_result_stays_private_skip_a_blanked_filter(
        self, pointer_filter: Path, args: tuple[str, ...], tolerates: bool
    ) -> None:
        argv = hardened_git_argv(args, repo_dir=pointer_filter)

        assert "filter.evil.clean=" in argv
        assert ("filter.evil.required=false" in argv) is tolerates


class TestRebaseRunsNoRepositoryProgram:
    @pytest.fixture
    def behind(self, tmp_path: Path) -> Path:
        """A clone one commit behind its upstream, with a dirty file the rebase has to autostash."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        git(upstream, "init", "-q")
        git(upstream, "config", "user.email", "a@example.com")
        git(upstream, "config", "user.name", "a")
        _commit_file(upstream, "f.txt", "one\n", "first")
        clone = tmp_path / "clone"
        run(["git", "clone", "-q", str(upstream), str(clone)], tmp_path)
        git(clone, "config", "user.email", "a@example.com")
        git(clone, "config", "user.name", "a")
        _commit_file(upstream, "g.txt", "g\n", "upstream moves on")
        git(clone, "fetch", "-q")
        git(clone, "status", "--porcelain")  # an index must exist before git consults the monitor
        (clone / "f.txt").write_text("dirty\n")
        return clone

    @staticmethod
    def _plant(clone: Path, markers: Path) -> None:
        for name in ("pre-rebase", "post-checkout", "post-rewrite"):
            _hook(clone, markers, name)
        git(clone, "config", "core.fsmonitor", program(markers, "fsmonitor"))

    def test_hooks_and_fsmonitor_stay_silent_and_the_rebase_succeeds(
        self, behind: Path, markers: Path, tmp_path: Path
    ) -> None:
        control = tmp_path / "control"
        shutil.copytree(behind, control, symlinks=True)
        self._plant(control, markers)
        run(plain(control, "rebase", "--autostash", "@{u}"), control)
        if "hook-pre-rebase" not in fired(markers):
            pytest.skip("this git build does not run the pre-rebase hook here")
        clear(markers)

        self._plant(behind, markers)
        hardened = run(hardened_git_argv(("rebase", "--autostash", "@{u}"), repo_dir=behind), behind)

        assert fired(markers) == set()
        assert hardened.returncode == 0, hardened.stderr
        assert run(plain(behind, "rev-list", "--count", "HEAD..@{u}"), behind).stdout.strip() == b"0"
        assert (behind / "f.txt").read_text() == "dirty\n", "the autostashed edit must come back"


class TestCallerConfig:
    def test_it_follows_the_hardened_overrides_so_a_commit_identity_can_be_supplied(self, repo: Path) -> None:
        git(repo, "config", "--unset", "user.email")
        git(repo, "config", "--unset", "user.name")
        git(repo, "add", "f.txt")
        config = ("user.name=Task Runner", "user.email=task@example.com")

        argv = hardened_git_argv(("commit", "-m", "x"), repo_dir=repo, config=config)
        result = run(argv, repo)

        assert argv.index("user.name=Task Runner") > argv.index("core.hooksPath=/dev/null")
        assert result.returncode == 0, result.stderr
        assert (
            run(plain(repo, "log", "-1", "--format=%an <%ae>"), repo).stdout.strip()
            == b"Task Runner <task@example.com>"
        )

    @pytest.mark.parametrize(
        "item", ["core.hooksPath=/tmp/mine", "commit.gpgsign=true", "protocol.ssh.allow=always", "noequals"]
    )
    def test_it_cannot_undo_a_hardened_key_or_be_malformed(self, repo: Path, item: str) -> None:
        with pytest.raises(ValueError, match="key=value"):
            hardened_git_argv(("status",), repo_dir=repo, config=(item,))
