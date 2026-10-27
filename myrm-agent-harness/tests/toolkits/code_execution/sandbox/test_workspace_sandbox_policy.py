"""The workspace sandbox policy factory grants a workspace tree or refuses it, never half-grants it.

[INPUT]
- code_execution.sandbox.policy_bridge (POS: The one place a workspace root becomes a writable sandbox tree)

[OUTPUT]
- Verdicts for ordinary, read-only, ancestor-of-dangerous-root and inside-dangerous-root workspaces, plus the protected git metadata the policy carries.

[POS]
Guards the grant point: a home directory or drive root must not become the sandbox's writable root.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.sandbox.policy_bridge import (
    UnsafeWorkspaceError,
    build_workspace_sandbox_policy,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / "proj").mkdir()
    monkeypatch.setattr(
        "myrm_agent_harness.core.security.path.filesystem.DANGEROUS_PATHS",
        frozenset({os.path.realpath(home / ".ssh")}),
    )
    return home


def test_ordinary_workspace_becomes_the_only_writable_tree(fake_home: Path) -> None:
    policy = build_workspace_sandbox_policy(str(fake_home / "proj"), allow_network=False)

    assert policy.writable_paths == (os.path.normpath(fake_home / "proj"),)
    assert policy.allow_network is False


def test_read_only_run_grants_nothing_even_for_a_broad_root(fake_home: Path) -> None:
    policy = build_workspace_sandbox_policy(str(fake_home), readonly=True)

    assert policy.writable_paths == ()
    assert policy.allow_network is True


@pytest.mark.parametrize("level", ["home", "above_home"])
def test_root_that_contains_a_dangerous_root_is_refused(fake_home: Path, level: str) -> None:
    root = fake_home if level == "home" else fake_home.parent

    with pytest.raises(UnsafeWorkspaceError, match="Workspace root cannot be granted write access"):
        build_workspace_sandbox_policy(str(root))


def test_the_dangerous_root_itself_is_refused(fake_home: Path) -> None:
    with pytest.raises(UnsafeWorkspaceError):
        build_workspace_sandbox_policy(str(fake_home / ".ssh"))


def test_workspace_inside_a_dangerous_root_is_granted_for_its_own_subtree(fake_home: Path) -> None:
    inside = fake_home / ".ssh" / "backup"
    inside.mkdir()

    assert build_workspace_sandbox_policy(str(inside)).writable_paths == (os.path.normpath(inside),)


def test_policy_keeps_the_git_config_and_hooks_of_the_workspace_read_only(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    (git_dir / "hooks").mkdir(parents=True)
    (git_dir / "config").write_text("[core]\n")

    policy = build_workspace_sandbox_policy(str(tmp_path))

    assert policy.read_only_subpaths == tuple(os.path.join(os.path.realpath(git_dir), n) for n in ("config", "hooks"))


def test_read_only_run_protects_nothing_because_nothing_is_writable(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")

    assert build_workspace_sandbox_policy(str(tmp_path), readonly=True).read_only_subpaths == ()


def test_real_home_and_filesystem_root_are_refused() -> None:
    for root in ("~", "/"):
        with pytest.raises(UnsafeWorkspaceError):
            build_workspace_sandbox_policy(root)


def test_empty_root_is_refused() -> None:
    with pytest.raises(UnsafeWorkspaceError):
        build_workspace_sandbox_policy("")
