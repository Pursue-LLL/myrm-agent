"""The approval payload names the folders "also grant folder access" would add, and the grant follows the plan.

The harness plans the grant once from the tool arguments and the effective path policy; the card shows that
plan and the approval applies it, independent of how the approval reason is worded.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolCall

from myrm_agent_harness.agent.middlewares._session_context import get_workspace_root, set_workspace_root
from myrm_agent_harness.agent.middlewares.approval._batch_decisions import apply_approval_decisions
from myrm_agent_harness.agent.middlewares.approval._interrupt_payload import build_interrupt_payload
from myrm_agent_harness.agent.security.session_access import (
    get_session_access_roots,
    grant_session_access_root,
    merge_path_policy_with_session_access,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import AccessRoot, PathPolicy, SecurityConfig

_POLICY = PathPolicy(forbidden_paths=frozenset(), access_roots=())


@pytest.fixture
def dirs(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    workspace = tmp_path / "ws"
    downloads = tmp_path / "downloads"
    for directory in (workspace, downloads):
        directory.mkdir()
    set_session_access_roots(())
    previous = get_workspace_root()
    set_workspace_root(str(workspace))
    try:
        yield workspace, downloads
    finally:
        set_workspace_root(previous)
        set_session_access_roots(())


def _call(name: str, args: dict[str, object], call_id: str = "c1") -> ToolCall:
    return ToolCall(type="tool_call", name=name, args=args, id=call_id)


def _payload(call: ToolCall, permission_type: str, workspace: Path, policy: PathPolicy | None = _POLICY) -> dict:
    payload, _ = build_interrupt_payload(
        [(0, call, permission_type, "needs approval", None)],
        "session-1",
        workspace_root=str(workspace),
        path_policy=policy,
    )
    return payload["actionRequests"][0]


def test_an_outside_read_carries_the_read_only_folder(dirs: tuple[Path, Path]) -> None:
    workspace, downloads = dirs
    request = _payload(_call("file_read_tool", {"paths": [f"{downloads}/a.csv:1-5"]}), "file_read", workspace)

    assert request["grantDirectories"] == [{"path": os.path.realpath(downloads), "writable": False}]


def test_an_outside_write_carries_the_read_write_folder(dirs: tuple[Path, Path]) -> None:
    workspace, downloads = dirs
    request = _payload(_call("file_write_tool", {"file_path": f"{downloads}/out.csv"}), "file_write", workspace)

    assert request["grantDirectories"] == [{"path": os.path.realpath(downloads), "writable": True}]


def test_a_search_of_an_outside_directory_carries_that_directory(dirs: tuple[Path, Path]) -> None:
    workspace, downloads = dirs
    request = _payload(_call("grep_tool", {"pattern": "x", "path": str(downloads)}), "file_read", workspace)

    assert request["grantDirectories"] == [{"path": os.path.realpath(downloads), "writable": False}]


@pytest.mark.parametrize(
    "call",
    [
        _call("file_read_tool", {"paths": ["src/a.py"]}),
        _call("glob_tool", {"pattern": "*.csv"}),
        _call("bash_code_execute_tool", {"command": "ls /tmp"}),
    ],
)
def test_nothing_is_offered_when_no_outside_folder_is_named(dirs: tuple[Path, Path], call: ToolCall) -> None:
    workspace, _ = dirs

    assert "grantDirectories" not in _payload(call, "file_read", workspace)


def test_nothing_is_offered_without_a_path_policy(dirs: tuple[Path, Path]) -> None:
    workspace, downloads = dirs
    request = _payload(_call("file_read_tool", {"paths": [f"{downloads}/a.csv"]}), "file_read", workspace, None)

    assert "grantDirectories" not in request


def test_a_folder_already_granted_is_not_offered_again(dirs: tuple[Path, Path]) -> None:
    workspace, downloads = dirs
    grant_session_access_root(AccessRoot(path=str(downloads), writable=False), workspace_root=str(workspace))
    request = _payload(_call("file_read_tool", {"paths": [f"{downloads}/a.csv"]}), "file_read", workspace)

    assert "grantDirectories" not in request


async def test_the_grant_does_not_depend_on_the_wording_of_the_reason(dirs: tuple[Path, Path]) -> None:
    _, downloads = dirs
    call = _call("file_read_tool", {"paths": [f"{downloads}/a.csv"]})
    decisions = [{"type": "approve", "extensions": {"grantDirectory": True}}]

    await apply_approval_decisions(
        decisions,
        AIMessage(content="", tool_calls=[call]),
        [],
        [(0, call, "file_read", "路径不在允许的目录内，需要确认", None)],
        [0],
        {},
        config=SecurityConfig(path_policy=_POLICY),
    )

    assert [root.path for root in get_session_access_roots()] == [os.path.realpath(downloads)]


async def test_approving_without_the_toggle_grants_nothing(dirs: tuple[Path, Path]) -> None:
    _, downloads = dirs
    call = _call("file_read_tool", {"paths": [f"{downloads}/a.csv"]})

    await apply_approval_decisions(
        [{"type": "approve", "extensions": {}}],
        AIMessage(content="", tool_calls=[call]),
        [],
        [(0, call, "file_read", "needs approval", None)],
        [0],
        {},
        config=SecurityConfig(path_policy=_POLICY),
    )

    assert get_session_access_roots() == ()


async def test_a_write_into_a_read_only_grant_is_offered_and_applied_as_an_upgrade(dirs: tuple[Path, Path]) -> None:
    workspace, downloads = dirs
    grant_session_access_root(AccessRoot(path=str(downloads), writable=False), workspace_root=str(workspace))
    call = _call("file_write_tool", {"file_path": f"{downloads}/out.csv"})

    request = _payload(call, "file_write", workspace, merge_path_policy_with_session_access(_POLICY))
    assert request["grantDirectories"] == [{"path": os.path.realpath(downloads), "writable": True}]

    await apply_approval_decisions(
        [{"type": "approve", "extensions": {"grantDirectory": True}}],
        AIMessage(content="", tool_calls=[call]),
        [],
        [(0, call, "file_write", "needs approval", None)],
        [0],
        {},
        config=SecurityConfig(path_policy=_POLICY),
    )

    assert [(root.path, root.writable) for root in get_session_access_roots()] == [(os.path.realpath(downloads), True)]


async def test_an_edited_approval_grants_nothing(dirs: tuple[Path, Path]) -> None:
    _, downloads = dirs
    call = _call("file_read_tool", {"paths": [f"{downloads}/a.csv"]})

    await apply_approval_decisions(
        [{"type": "edit", "args": {"paths": [f"{downloads}/b.csv"]}, "extensions": {"grantDirectory": True}}],
        AIMessage(content="", tool_calls=[call]),
        [],
        [(0, call, "file_read", "needs approval", None)],
        [0],
        {},
        config=SecurityConfig(path_policy=_POLICY),
    )

    assert get_session_access_roots() == ()
