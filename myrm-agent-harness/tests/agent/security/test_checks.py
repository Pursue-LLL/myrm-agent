"""Tests for checks.py (Path Policy, Scheme, and Threat checks)."""

from __future__ import annotations

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
