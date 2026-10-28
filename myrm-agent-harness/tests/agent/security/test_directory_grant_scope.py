"""What "also grant folder access" may offer: nothing when the host forbids widening, no write grant over a home.

A host that must keep a run inside its workspace (an isolated worktree) sets ``allow_directory_grants=False``:
the permission engine then refuses a path outside the zones outright instead of asking about a folder the grant
would drop, and the approval card offers no folder. A write grant that contains a dangerous root (a home
directory, ``/``) is never offered either, since the deployment gate refuses it after the person has ticked it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.config import parse_security_config
from myrm_agent_harness.agent.security.session_access import (
    get_session_access_roots,
    grant_directories_for_call,
    grant_session_access_root,
    plan_directory_grants,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import AccessRoot, PathPolicy, PermissionAction, access_roots_from_paths


@pytest.fixture(autouse=True)
def _no_session_grants() -> Iterator[None]:
    set_session_access_roots(())
    yield
    set_session_access_roots(())


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "spec.md").write_text("spec")
    return workspace, outside


_LOCKED = PathPolicy(allow_directory_grants=False)


def test_a_locked_policy_refuses_a_path_outside_the_zones_outright(dirs: tuple[Path, Path]) -> None:
    workspace, outside = dirs

    action, reason = check_path_policy(str(outside / "spec.md"), _LOCKED, str(workspace))

    assert action == PermissionAction.DENY
    assert str(outside / "spec.md") in reason


def test_a_locked_policy_still_serves_the_workspace_and_declared_roots(dirs: tuple[Path, Path]) -> None:
    workspace, outside = dirs
    policy = PathPolicy(allow_directory_grants=False, access_roots=access_roots_from_paths((str(outside),)))

    inside, _ = check_path_policy(str(workspace / "a.txt"), policy, str(workspace), require_write=True)
    declared, _ = check_path_policy(str(outside / "spec.md"), policy, str(workspace))

    assert inside == PermissionAction.ALLOW
    assert declared == PermissionAction.ALLOW


def test_an_unlocked_policy_still_asks_about_a_path_outside_the_zones(dirs: tuple[Path, Path]) -> None:
    workspace, outside = dirs

    action, _ = check_path_policy(str(outside / "spec.md"), PathPolicy(), str(workspace))

    assert action == PermissionAction.ASK


def test_a_locked_policy_offers_no_folder_and_grants_none(dirs: tuple[Path, Path]) -> None:
    workspace, outside = dirs
    args: dict[str, object] = {"file_path": str(outside / "spec.md")}

    assert plan_directory_grants(args, policy=_LOCKED, workspace_root=str(workspace), writable=False) == []
    assert grant_directories_for_call(args, policy=_LOCKED, workspace_root=str(workspace), writable=False) == []
    assert get_session_access_roots() == ()


def test_a_locked_policy_refuses_a_direct_grant(dirs: tuple[Path, Path]) -> None:
    workspace, outside = dirs

    roots = grant_session_access_root(
        AccessRoot(path=str(outside), writable=False), policy=_LOCKED, workspace_root=str(workspace)
    )

    assert roots == ()


def test_the_config_key_locks_the_policy() -> None:
    config = parse_security_config({"pathPolicy": {"allowDirectoryGrants": False}})

    assert config is not None
    assert config.path_policy.allow_directory_grants is False


def test_grants_stay_allowed_unless_the_config_says_otherwise() -> None:
    config = parse_security_config({"pathPolicy": {"allowedRoots": []}})

    assert config is not None
    assert config.path_policy.allow_directory_grants is True


class TestWriteGrantOverADangerousRoot:
    """A writable grant on a directory that contains a dangerous root reaches it through the tree."""

    def test_a_write_beside_the_filesystem_root_is_not_offered_a_grant_of_it(self, tmp_path: Path) -> None:
        plan = plan_directory_grants(
            {"file_path": os.path.join(os.sep, "no-such-file.txt")},
            policy=PathPolicy(),
            workspace_root=str(tmp_path),
            writable=True,
        )

        assert plan == []

    def test_a_write_into_a_home_directory_is_not_offered_a_grant_of_it(self, tmp_path: Path) -> None:
        plan = plan_directory_grants(
            {"file_path": os.path.join(os.path.expanduser("~"), "no-such-notes.txt")},
            policy=PathPolicy(),
            workspace_root=str(tmp_path),
            writable=True,
        )

        assert plan == []

    def test_the_same_read_is_still_offered_read_only(self, tmp_path: Path) -> None:
        home = os.path.realpath(os.path.expanduser("~"))

        plan = plan_directory_grants(
            {"file_path": os.path.join(home, "no-such-notes.txt")},
            policy=PathPolicy(),
            workspace_root=str(tmp_path),
            writable=False,
        )

        assert [(root.path, root.writable) for root in plan] == [(home, False)]

    def test_a_direct_write_grant_of_a_home_directory_is_refused(self, tmp_path: Path) -> None:
        home = os.path.realpath(os.path.expanduser("~"))

        roots = grant_session_access_root(
            AccessRoot(path=home, writable=True), policy=PathPolicy(), workspace_root=str(tmp_path)
        )

        assert roots == ()
