"""Seatbelt keeps a workspace's git metadata read-only and never lets a path write profile rules.

[INPUT]
- code_execution.sandbox.providers.seatbelt (POS: macOS sandbox-exec (Seatbelt) sandbox provider)
- code_execution.sandbox.policy_bridge (POS: The one place a workspace root becomes a writable sandbox tree)

[OUTPUT]
- Profile text checks plus real ``sandbox-exec`` runs: blocked config/hook/pointer writes, working git, quoted paths.

[POS]
Enforcement tests for ``SandboxPolicy.read_only_subpaths`` and the profile string escaping.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.sandbox.policy_bridge import build_workspace_sandbox_policy
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.seatbelt import (
    SeatbeltProvider,
    _generate_sbpl_profile,
    _sbpl_string,
)
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxPolicy

_requires_seatbelt = pytest.mark.skipif(
    sys.platform != "darwin" or not SeatbeltProvider().is_available() or shutil.which("git") is None,
    reason="needs macOS sandbox-exec and git",
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


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
    return workspace


def _sandboxed(workspace: Path, script: str, policy: SandboxPolicy) -> subprocess.CompletedProcess[str]:
    profile = _generate_sbpl_profile(policy, str(workspace))
    env = {**os.environ, "HOME": str(workspace.parent)}
    return subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", profile, "/bin/bash", "-c", script],
        cwd=workspace,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class TestProfileText:
    def test_string_literal_escapes_quote_and_backslash(self) -> None:
        assert _sbpl_string('a"b\\c') == '"a\\"b\\\\c"'

    def test_path_cannot_append_rules(self, tmp_path: Path) -> None:
        hostile = str(tmp_path / '") (allow file-write* (subpath "/')
        profile = _generate_sbpl_profile(SandboxPolicy(writable_paths=(hostile,)), hostile)

        assert '(subpath "/"))' not in profile
        assert '\\") (allow file-write*' in profile

    def test_read_only_rules_follow_the_writable_allow(self, tmp_path: Path) -> None:
        ws = os.path.realpath(tmp_path)
        policy = SandboxPolicy(writable_paths=(ws,), read_only_subpaths=(f"{ws}/.git/config",))

        lines = _generate_sbpl_profile(policy, ws).splitlines()

        allow = lines.index(f'(allow file-write* (subpath "{ws}"))')
        assert lines.index(f'(deny file-write* (subpath "{ws}/.git/config"))') > allow
        assert lines.index(f'(deny file-write* (literal "{ws}/.git"))') > allow

    def test_entry_held_directly_by_a_writable_root_is_not_pinned(self, tmp_path: Path) -> None:
        ws = os.path.realpath(tmp_path)
        policy = SandboxPolicy(writable_paths=(ws,), read_only_subpaths=(f"{ws}/.git",))

        assert f'(deny file-write* (literal "{ws}"))' not in _generate_sbpl_profile(policy, ws)


@_requires_seatbelt
class TestEnforcement:
    def test_config_hooks_and_the_git_directory_cannot_be_changed(self, repo: Path) -> None:
        policy = build_workspace_sandbox_policy(str(repo))
        before = (repo / ".git" / "config").read_text()

        attempts = {
            "config": "git config core.fsmonitor 'touch /tmp/never'",
            "hook": "printf '#!/bin/sh\\n' > .git/hooks/pre-commit",
            "rename_git_dir": "mv .git .git_old",
            "replace_config": "rm .git/config && printf '[core]\\n' > .git/config",
        }
        for name, script in attempts.items():
            result = _sandboxed(repo, script, policy)
            assert result.returncode != 0, name

        assert (repo / ".git").is_dir()
        assert (repo / ".git" / "config").read_text() == before
        assert not (repo / ".git" / "hooks" / "pre-commit").exists()

    def test_pointer_redirect_through_the_git_directory_is_blocked(self, repo: Path, tmp_path: Path) -> None:
        policy = build_workspace_sandbox_policy(str(repo))
        evil = tmp_path / "evil"

        result = _sandboxed(
            repo,
            f"mv .git .git_old && printf 'gitdir: {evil}\\n' > .git",
            policy,
        )

        assert result.returncode != 0
        assert (repo / ".git").is_dir()

    def test_day_to_day_git_and_file_work_still_succeeds(self, repo: Path) -> None:
        policy = build_workspace_sandbox_policy(str(repo))
        script = " && ".join(
            [
                "echo two >> f.txt",
                "mkdir -p src && echo x > src/a.py",
                "git add -A",
                "git commit -q -m second",
                "git checkout -q -b feature",
                "echo three >> f.txt && git commit -q -am third",
                "git checkout -q -",
                "git merge -q --no-edit feature",
                "git stash list",
                "git tag v1",
                "git log --oneline",
                "git status --porcelain",
            ]
        )

        result = _sandboxed(repo, script, policy)

        assert result.returncode == 0, result.stderr
        assert (repo / "src" / "a.py").exists()

    def test_without_the_protected_paths_the_same_write_succeeds(self, repo: Path) -> None:
        unprotected = SandboxPolicy(writable_paths=(str(repo),))

        assert _sandboxed(repo, "git config core.fsmonitor false", unprotected).returncode == 0

    def test_workspace_path_with_a_quote_neither_breaks_nor_widens_the_profile(self, tmp_path: Path) -> None:
        victim = tmp_path / "victim"
        victim.mkdir()
        hostile = tmp_path / f'x")) (allow file-write* (subpath "{victim}'
        hostile.mkdir(parents=True)
        policy = build_workspace_sandbox_policy(str(hostile))

        inside = _sandboxed(hostile, "echo ok > inside.txt", policy)
        outside = _sandboxed(hostile, f"echo pwned > '{victim}/marker'", policy)

        assert inside.returncode == 0, inside.stderr
        assert outside.returncode != 0
        assert not (victim / "marker").exists()
