"""Tests for checks.py (Path Policy, Scheme, and Threat checks)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.types import (
    AccessRoot,
    PathPolicy,
    PermissionAction,
)


def test_check_path_policy_forbidden_path() -> None:
    policy = PathPolicy(
        forbidden_paths=("/etc", "/sys"),
        access_roots=(),
    )
    action, reason = check_path_policy("/etc/passwd", policy, workspace_root=None)
    assert action == PermissionAction.DENY
    assert "forbidden zone" in reason


def test_check_path_policy_workspace_allow() -> None:
    workspace = "/tmp/my_workspace"
    policy = PathPolicy(forbidden_paths=(), access_roots=())
    action, reason = check_path_policy(
        "/tmp/my_workspace/src/app.py",
        policy,
        workspace_root=workspace,
        require_write=True,
    )
    assert action == PermissionAction.ALLOW
    assert reason == ""


def test_check_path_policy_readonly_root_read() -> None:
    policy = PathPolicy(
        forbidden_paths=(),
        access_roots=(AccessRoot(path="/data/readonly", writable=False),),
    )
    action, reason = check_path_policy(
        "/data/readonly/doc.txt",
        policy,
        workspace_root=None,
        require_write=False,
    )
    assert action == PermissionAction.ALLOW
    assert reason == ""


def test_check_path_policy_readonly_root_write_triggers_ask() -> None:
    policy = PathPolicy(
        forbidden_paths=(),
        access_roots=(AccessRoot(path="/data/readonly", writable=False),),
    )
    action, reason = check_path_policy(
        "/data/readonly/doc.txt",
        policy,
        workspace_root=None,
        require_write=True,
    )
    assert action == PermissionAction.ASK
    assert "write permission required" in reason


def test_check_path_policy_outside_zone_triggers_ask() -> None:
    policy = PathPolicy(
        forbidden_paths=(),
        access_roots=(AccessRoot(path="/data/allowed", writable=True),),
    )
    action, reason = check_path_policy(
        "/var/other/file.txt",
        policy,
        workspace_root=None,
        require_write=False,
    )
    assert action == PermissionAction.ASK
    assert "Path outside allowed zones" in reason


def test_check_path_policy_reads_container_alias_as_workspace_file(tmp_path) -> None:
    workspace = str(tmp_path)
    policy = PathPolicy(forbidden_paths=(), access_roots=())
    action, _ = check_path_policy("/workspace/src/app.py", policy, workspace_root=workspace, require_write=True)
    assert action == PermissionAction.ALLOW


def test_check_path_policy_forbidden_path_cannot_be_dodged_through_container_alias(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    secret = workspace / "secret"
    policy = PathPolicy(forbidden_paths=(str(secret),), access_roots=())

    direct, _ = check_path_policy(str(secret / "key.txt"), policy, workspace_root=str(workspace))
    aliased, reason = check_path_policy("/workspace/secret/key.txt", policy, workspace_root=str(workspace))

    assert direct == PermissionAction.DENY
    assert aliased == PermissionAction.DENY
    assert "forbidden zone" in reason


def test_check_path_policy_lookalike_of_container_alias_is_outside_workspace(tmp_path) -> None:
    policy = PathPolicy(forbidden_paths=(), access_roots=())
    action, _ = check_path_policy("/workspace2/app.py", policy, workspace_root=str(tmp_path))
    assert action == PermissionAction.ASK


def test_check_path_policy_without_workspace_leaves_container_alias_untouched() -> None:
    policy = PathPolicy(forbidden_paths=(), access_roots=())
    action, _ = check_path_policy("/workspace/app.py", policy, workspace_root=None)
    assert action == PermissionAction.ASK


# A link is judged by the file it leads to: ``notes.txt -> .env`` is the credential file, whatever it is called.

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")


@pytest.fixture
def linked_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".env").write_text("CANARY=1")
    (root / "plan.md").write_text("plan")
    (root / "notes.txt").symlink_to(".env")
    (root / "alias.md").symlink_to("plan.md")
    return root


@POSIX_ONLY
def test_check_path_policy_asks_for_a_link_that_leads_to_a_credential_file(linked_workspace: Path) -> None:
    action, reason = check_path_policy("notes.txt", PathPolicy(), workspace_root=str(linked_workspace))

    assert action == PermissionAction.ASK
    assert "Sensitive file: .env" in reason


@POSIX_ONLY
@pytest.mark.parametrize("writable", [True, False], ids=["writable-grant", "read-only-grant"])
def test_check_path_policy_asks_for_such_a_link_in_a_granted_directory(linked_workspace: Path, writable: bool) -> None:
    policy = PathPolicy(access_roots=(AccessRoot(path=str(linked_workspace), writable=writable),))

    action, reason = check_path_policy(str(linked_workspace / "notes.txt"), policy, workspace_root=None)

    assert action == PermissionAction.ASK
    assert "Sensitive file: .env" in reason


@POSIX_ONLY
def test_check_path_policy_allows_a_link_to_an_ordinary_file(linked_workspace: Path) -> None:
    action, reason = check_path_policy("alias.md", PathPolicy(), workspace_root=str(linked_workspace))

    assert action == PermissionAction.ALLOW
    assert reason == ""


def test_check_path_policy_does_not_read_the_workspace_location_as_a_credential_name(tmp_path: Path) -> None:
    # The real path of ``.envs/ws/src/app.py`` has a ``.envs`` directory above the file; a rule names the file.
    root = tmp_path / ".envs" / "ws"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print()")

    action, _ = check_path_policy("src/app.py", PathPolicy(), workspace_root=str(root))

    assert action == PermissionAction.ALLOW


# The engine reads a typed path the way the file tools open it: ``~`` is the home, nothing else is expanded.


@POSIX_ONLY
def test_check_path_policy_follows_a_link_named_like_an_environment_variable(
    linked_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Expanding the name first would resolve some other path and hide the link from the realpath.
    monkeypatch.setenv("MYRM_LINKED", "expanded")
    (linked_workspace / "$MYRM_LINKED").symlink_to(".env")

    action, reason = check_path_policy("$MYRM_LINKED", PathPolicy(), workspace_root=str(linked_workspace))

    assert action == PermissionAction.ASK
    assert "Sensitive file: .env" in reason


@pytest.mark.parametrize("typed", ["$MYRM_UP/notes.txt", "~root/notes.txt", "~$notes.txt"])
def test_check_path_policy_reads_other_spellings_as_workspace_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, typed: str
) -> None:
    monkeypatch.setenv("MYRM_UP", "../elsewhere")
    root = tmp_path / "ws"
    root.mkdir()

    action, _ = check_path_policy(typed, PathPolicy(), workspace_root=str(root))

    assert action == PermissionAction.ALLOW


def test_check_path_policy_reads_a_home_spelling_as_the_home_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(home))
    root = tmp_path / "ws"
    root.mkdir()

    action, reason = check_path_policy("~/notes.txt", PathPolicy(), workspace_root=str(root))

    assert action == PermissionAction.ASK
    assert "outside allowed zones" in reason
