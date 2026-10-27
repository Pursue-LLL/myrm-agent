"""Tests for session access grants and path policy readonly roots."""

from __future__ import annotations

import os

from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.session_access import (
    get_session_access_roots,
    grant_directories_for_call,
    grant_session_access_root,
    merge_path_policy_with_session_access,
    resolve_grant_directory_path,
    revoke_session_access_root,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import (
    AccessRoot,
    PathPolicy,
    PermissionAction,
    access_roots_from_paths,
)


def test_readonly_root_allows_read_prompts_write_elevation(tmp_path) -> None:
    ref = tmp_path / "ref"
    ref.mkdir()
    policy = PathPolicy(access_roots=access_roots_from_paths((str(ref),), writable=False))
    read_action, _ = check_path_policy(
        str(ref / "doc.txt"),
        policy,
        workspace_root=str(tmp_path / "ws"),
        require_write=False,
    )
    write_action, reason = check_path_policy(
        str(ref / "doc.txt"),
        policy,
        workspace_root=str(tmp_path / "ws"),
        require_write=True,
    )
    assert read_action == PermissionAction.ALLOW
    assert write_action == PermissionAction.ASK
    assert "read-only" in reason


def test_session_grant_merged_into_policy(tmp_path) -> None:
    set_session_access_roots(())
    downloads = os.path.realpath(str(tmp_path / "downloads"))
    os.makedirs(downloads, exist_ok=True)
    grant_session_access_root(
        AccessRoot(path=downloads, writable=False, source="hitl_grant"),
    )
    merged = merge_path_policy_with_session_access(PathPolicy())
    assert any(r.path == downloads for r in merged.access_roots)


def test_resolve_grant_directory_path_uses_workspace_for_relative(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    rel = os.path.relpath(outside, workspace)
    resolved = resolve_grant_directory_path(rel, str(workspace))
    assert resolved == os.path.realpath(str(outside))


def test_grant_rejects_forbidden_path(tmp_path) -> None:
    set_session_access_roots(())
    forbidden_root = tmp_path / "secret"
    forbidden_root.mkdir()
    policy = PathPolicy(forbidden_paths=(str(forbidden_root),))
    before = grant_session_access_root(
        AccessRoot(path=str(forbidden_root), writable=False, source="hitl_grant"),
        policy=policy,
        workspace_root=str(tmp_path / "ws"),
    )
    assert before == ()


def test_session_grant_allows_subsequent_read(tmp_path) -> None:
    set_session_access_roots(())
    workspace = tmp_path / "ws"
    workspace.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    doc = downloads / "invoice.pdf"
    doc.write_text("ok", encoding="utf-8")

    grant_session_access_root(
        AccessRoot(path=str(downloads), writable=False, source="hitl_grant"),
        policy=PathPolicy(),
        workspace_root=str(workspace),
    )
    merged = merge_path_policy_with_session_access(PathPolicy())
    action, _ = check_path_policy(
        str(doc),
        merged,
        workspace_root=str(workspace),
        require_write=False,
    )
    assert action == PermissionAction.ALLOW


def test_revoke_session_access_root_removes_grant(tmp_path) -> None:
    set_session_access_roots(())
    workspace = tmp_path / "ws"
    workspace.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    grant_session_access_root(
        AccessRoot(path=str(downloads), writable=False, source="hitl_grant"),
        workspace_root=str(workspace),
    )
    assert len(get_session_access_roots()) == 1

    revoke_session_access_root(str(downloads), workspace_root=str(workspace))
    assert get_session_access_roots() == ()


def test_revoke_unknown_path_is_noop(tmp_path) -> None:
    set_session_access_roots(())
    workspace = tmp_path / "ws"
    workspace.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    grant_session_access_root(
        AccessRoot(path=str(downloads), writable=False, source="hitl_grant"),
        workspace_root=str(workspace),
    )
    revoke_session_access_root(str(tmp_path / "other"), workspace_root=str(workspace))
    assert len(get_session_access_roots()) == 1


class TestGrantDirectoriesForCall:
    """The directories a user approves for a file call: one per file outside the allowed zones, whatever the argument is called."""

    @staticmethod
    def _dirs(tmp_path) -> tuple[str, str, str]:
        workspace = tmp_path / "ws"
        downloads = tmp_path / "downloads"
        reports = tmp_path / "reports"
        for directory in (workspace, downloads, reports):
            directory.mkdir()
        return str(workspace), os.path.realpath(downloads), os.path.realpath(reports)

    def test_every_outside_file_of_a_batched_read_is_granted_its_directory(self, tmp_path) -> None:
        set_session_access_roots(())
        workspace, downloads, reports = self._dirs(tmp_path)
        granted = grant_directories_for_call(
            {"paths": [f"{downloads}/a.csv", "src/inside.py", f"{reports}/b.csv:1-20"]},
            policy=PathPolicy(forbidden_paths=frozenset(), access_roots=()),
            workspace_root=workspace,
            writable=False,
        )
        assert granted == [downloads, reports]
        assert [root.path for root in get_session_access_roots()] == [downloads, reports]
        assert all(not root.writable and root.source == "path_ask_grant" for root in get_session_access_roots())
        set_session_access_roots(())

    def test_files_inside_the_workspace_never_use_up_a_grant(self, tmp_path) -> None:
        set_session_access_roots(())
        workspace, _, _ = self._dirs(tmp_path)
        granted = grant_directories_for_call(
            {"paths": ["src/a.py", f"{workspace}/b.py"]},
            policy=PathPolicy(forbidden_paths=frozenset(), access_roots=()),
            workspace_root=workspace,
            writable=False,
        )
        assert granted == []
        assert get_session_access_roots() == ()

    def test_two_files_of_one_directory_grant_it_once(self, tmp_path) -> None:
        set_session_access_roots(())
        workspace, downloads, _ = self._dirs(tmp_path)
        granted = grant_directories_for_call(
            {"files": [f"{downloads}/a.csv", f"{downloads}/b.csv"]},
            policy=PathPolicy(forbidden_paths=frozenset(), access_roots=()),
            workspace_root=workspace,
            writable=True,
        )
        assert granted == [downloads]
        assert get_session_access_roots()[0].writable
        set_session_access_roots(())

    def test_a_forbidden_directory_is_never_granted(self, tmp_path) -> None:
        set_session_access_roots(())
        workspace, downloads, _ = self._dirs(tmp_path)
        granted = grant_directories_for_call(
            {"paths": [f"{downloads}/id_rsa"]},
            policy=PathPolicy(forbidden_paths=frozenset({downloads})),
            workspace_root=workspace,
            writable=False,
        )
        assert granted == []
        assert get_session_access_roots() == ()

    def test_a_call_naming_no_host_file_grants_nothing(self, tmp_path) -> None:
        set_session_access_roots(())
        workspace, _, _ = self._dirs(tmp_path)
        granted = grant_directories_for_call(
            {"paths": ["/mcp/gmail/send_email.md", "https://example.com/a"], "pattern": "*"},
            policy=PathPolicy(forbidden_paths=frozenset(), access_roots=()),
            workspace_root=workspace,
            writable=False,
        )
        assert granted == []
