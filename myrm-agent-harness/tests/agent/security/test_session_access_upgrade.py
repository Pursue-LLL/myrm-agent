"""A write grant raises a held read-only folder to writable; the plan offers exactly what the grant changes."""

from __future__ import annotations

import os

import pytest

from myrm_agent_harness.agent.security.session_access import (
    get_session_access_roots,
    grant_directories_for_call,
    grant_session_access_root,
    merge_path_policy_with_session_access,
    plan_directory_grants,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import AccessRoot, PathPolicy


class TestGrantUpgrade:
    """A read-only grant is raised to writable by an explicit write grant, never lowered or duplicated."""

    @staticmethod
    def _held(tmp_path, *, writable: bool) -> tuple[str, str]:
        set_session_access_roots(())
        workspace = tmp_path / "ws"
        docs = tmp_path / "docs"
        for directory in (workspace, docs):
            directory.mkdir()
        grant_session_access_root(
            AccessRoot(path=str(docs), writable=writable, source="desktop_drag_drop", label="Docs"),
            workspace_root=str(workspace),
        )
        return str(workspace), str(docs)

    def test_a_write_grant_raises_a_held_read_only_root_in_place(self, tmp_path) -> None:
        workspace, docs = self._held(tmp_path, writable=False)
        updated = grant_session_access_root(AccessRoot(path=docs, writable=True), workspace_root=workspace)
        assert [(root.path, root.writable, root.source, root.label) for root in updated] == [
            (os.path.realpath(docs), True, "desktop_drag_drop", "Docs")
        ]
        assert get_session_access_roots() == updated
        set_session_access_roots(())

    def test_a_read_grant_never_lowers_a_held_writable_root(self, tmp_path) -> None:
        workspace, docs = self._held(tmp_path, writable=True)
        before = get_session_access_roots()
        assert grant_session_access_root(AccessRoot(path=docs, writable=False), workspace_root=workspace) == before
        assert [root.writable for root in get_session_access_roots()] == [True]
        set_session_access_roots(())

    def test_the_upgrade_is_refused_where_the_policy_forbids_writing(self, tmp_path) -> None:
        workspace, docs = self._held(tmp_path, writable=False)
        before = get_session_access_roots()
        policy = PathPolicy(forbidden_paths=frozenset({docs}))
        assert (
            grant_session_access_root(AccessRoot(path=docs, writable=True), policy=policy, workspace_root=workspace)
            == before
        )
        set_session_access_roots(())

    def test_the_call_reports_an_upgraded_folder_as_granted(self, tmp_path) -> None:
        workspace, docs = self._held(tmp_path, writable=False)
        granted = grant_directories_for_call(
            {"file_path": f"{docs}/out.txt"},
            policy=merge_path_policy_with_session_access(PathPolicy(forbidden_paths=frozenset(), access_roots=())),
            workspace_root=workspace,
            writable=True,
        )
        assert granted == [os.path.realpath(docs)]
        assert [root.writable for root in get_session_access_roots()] == [True]
        set_session_access_roots(())


@pytest.mark.parametrize("held", [None, False, True], ids=["nothing-held", "held-read-only", "held-writable"])
@pytest.mark.parametrize("writable", [False, True], ids=["read-call", "write-call"])
def test_every_folder_the_plan_offers_is_one_the_grant_changes(tmp_path, held: bool | None, writable: bool) -> None:
    """The card never promises a folder the grant then leaves as it was, whatever the folder already held."""
    set_session_access_roots(())
    workspace = tmp_path / "ws"
    docs = tmp_path / "docs"
    for directory in (workspace, docs):
        directory.mkdir()
    if held is not None:
        grant_session_access_root(AccessRoot(path=str(docs), writable=held), workspace_root=str(workspace))
    policy = merge_path_policy_with_session_access(PathPolicy(forbidden_paths=frozenset(), access_roots=()))
    call = {"file_path": f"{docs}/out.txt"}

    offered = [
        root.path
        for root in plan_directory_grants(call, policy=policy, workspace_root=str(workspace), writable=writable)
    ]
    granted = grant_directories_for_call(call, policy=policy, workspace_root=str(workspace), writable=writable)

    assert granted == offered
    set_session_access_roots(())
