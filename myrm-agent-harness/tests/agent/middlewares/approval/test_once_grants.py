"""Approving a call opens the files it names for that call alone; the toggle is what keeps their folders.

The card promises exactly this: "Allow" lets the call touch what it asked for, "also grant folder access" remembers
the folder for the session. Without the first the executor refuses a call the person just approved.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolCall

from myrm_agent_harness.agent.middlewares._session_context import get_workspace_root, set_workspace_root
from myrm_agent_harness.agent.middlewares.approval._batch_decisions import apply_approval_decisions
from myrm_agent_harness.agent.middlewares.approval.middleware import ToolApprovalMiddleware
from myrm_agent_harness.agent.security.session_access import (
    drop_once_grants,
    get_session_access_roots,
    grant_paths_once,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import PathPolicy, SecurityConfig
from myrm_agent_harness.core.context_vars import (
    AccessGrants,
    access_grants_var,
    open_access_grants,
    reachable_access_roots,
    scoped_value,
)

_POLICY = PathPolicy(forbidden_paths=frozenset(), access_roots=())


@pytest.fixture
def run(tmp_path: Path) -> Iterator[tuple[Path, Path, AccessGrants]]:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    previous = get_workspace_root()
    set_workspace_root(str(workspace))
    with scoped_value(access_grants_var, None):
        set_session_access_roots(())
        grants = open_access_grants(())
        try:
            yield workspace, outside.resolve(), grants
        finally:
            set_session_access_roots(())
            set_workspace_root(previous)


def _call(name: str, args: dict[str, object]) -> ToolCall:
    return ToolCall(type="tool_call", name=name, args=args, id="c1")


async def _decide(call: ToolCall, permission_type: str, decision: dict[str, object], policy: PathPolicy) -> None:
    await apply_approval_decisions(
        [decision],
        AIMessage(content="", tool_calls=[call]),
        [],
        [(0, call, permission_type, "needs approval", None)],
        [0],
        {},
        config=SecurityConfig(path_policy=policy),
    )


def _once_paths(grants: AccessGrants) -> list[tuple[str, bool]]:
    return [(root.path, root.writable) for root in grants.once]


async def test_approving_a_read_opens_the_named_file_read_only_and_remembers_nothing(
    run: tuple[Path, Path, AccessGrants],
) -> None:
    _, outside, grants = run
    call = _call("file_read_tool", {"paths": [f"{outside}/a.csv"]})

    await _decide(call, "file_read", {"type": "approve", "extensions": {}}, _POLICY)

    assert _once_paths(grants) == [(os.path.join(outside, "a.csv"), False)]
    assert get_session_access_roots() == ()


async def test_approving_a_write_opens_the_named_file_writable(run: tuple[Path, Path, AccessGrants]) -> None:
    _, outside, grants = run
    call = _call("file_write_tool", {"file_path": f"{outside}/out.csv"})

    await _decide(call, "file_write", {"type": "approve", "extensions": {}}, _POLICY)

    assert _once_paths(grants) == [(os.path.join(outside, "out.csv"), True)]


async def test_the_toggle_also_keeps_the_folder_for_the_session(run: tuple[Path, Path, AccessGrants]) -> None:
    _, outside, grants = run
    call = _call("file_read_tool", {"paths": [f"{outside}/a.csv"]})

    await _decide(call, "file_read", {"type": "approve", "extensions": {"grantDirectory": True}}, _POLICY)

    assert [root.path for root in grants.session] == [str(outside)]
    assert _once_paths(grants) == [(os.path.join(outside, "a.csv"), False)]


async def test_a_refused_call_opens_nothing(run: tuple[Path, Path, AccessGrants]) -> None:
    _, outside, grants = run
    call = _call("file_read_tool", {"paths": [f"{outside}/a.csv"]})

    await _decide(call, "file_read", {"type": "reject"}, _POLICY)

    assert grants.once == ()


async def test_an_edited_call_opens_nothing(run: tuple[Path, Path, AccessGrants]) -> None:
    _, outside, grants = run
    call = _call("file_read_tool", {"paths": [f"{outside}/a.csv"]})

    await _decide(call, "file_read", {"type": "edit", "args": {"paths": [f"{outside}/b.csv"]}}, _POLICY)

    assert grants.once == ()


def test_a_path_inside_the_workspace_opens_nothing(run: tuple[Path, Path, AccessGrants]) -> None:
    workspace, _, grants = run

    opened = grant_paths_once(
        {"file_path": f"{workspace}/AGENTS.md"}, policy=_POLICY, workspace_root=str(workspace), writable=True
    )

    assert opened == []
    assert grants.once == ()


def test_a_host_that_keeps_the_run_inside_its_zones_opens_nothing(run: tuple[Path, Path, AccessGrants]) -> None:
    workspace, outside, grants = run
    locked = PathPolicy(forbidden_paths=frozenset(), access_roots=(), allow_directory_grants=False)

    opened = grant_paths_once(
        {"paths": [f"{outside}/a.csv"]}, policy=locked, workspace_root=str(workspace), writable=False
    )

    assert opened == []
    assert grants.once == ()


def test_a_writable_grant_over_a_home_directory_is_refused(run: tuple[Path, Path, AccessGrants]) -> None:
    workspace, _, grants = run

    opened = grant_paths_once(
        {"file_path": os.path.expanduser("~")}, policy=_POLICY, workspace_root=str(workspace), writable=True
    )

    assert opened == []
    assert grants.once == ()


def test_a_run_that_never_opened_grants_has_nowhere_to_keep_them(tmp_path: Path) -> None:
    with scoped_value(access_grants_var, None):
        opened = grant_paths_once(
            {"paths": [f"{tmp_path}/a.csv"]}, policy=_POLICY, workspace_root=str(tmp_path / "ws"), writable=False
        )

    assert opened == []


def test_the_same_file_is_opened_once_and_a_write_upgrades_it(run: tuple[Path, Path, AccessGrants]) -> None:
    workspace, outside, grants = run
    args: dict[str, object] = {"paths": [f"{outside}/a.csv"]}

    grant_paths_once(args, policy=_POLICY, workspace_root=str(workspace), writable=False)
    grant_paths_once(args, policy=_POLICY, workspace_root=str(workspace), writable=False)
    assert _once_paths(grants) == [(os.path.join(outside, "a.csv"), False)]

    grant_paths_once(args, policy=_POLICY, workspace_root=str(workspace), writable=True)
    assert _once_paths(grants) == [(os.path.join(outside, "a.csv"), True)]


async def test_calls_of_one_response_approved_together_stay_open_until_the_next_response(
    run: tuple[Path, Path, AccessGrants],
) -> None:
    _, outside, grants = run
    read = _call("file_read_tool", {"paths": [f"{outside}/a.csv"]})
    write = ToolCall(type="tool_call", name="file_write_tool", args={"file_path": f"{outside}/b.csv"}, id="c2")

    await apply_approval_decisions(
        [{"type": "approve", "extensions": {}}, {"type": "approve", "extensions": {}}],
        AIMessage(content="", tool_calls=[read, write]),
        [],
        [(0, read, "file_read", "needs approval", None), (1, write, "file_write", "needs approval", None)],
        [0, 1],
        {},
        config=SecurityConfig(path_policy=_POLICY),
    )

    assert sorted(_once_paths(grants)) == [
        (os.path.join(outside, "a.csv"), False),
        (os.path.join(outside, "b.csv"), True),
    ]
    drop_once_grants()
    assert grants.once == ()


def test_the_next_model_response_closes_what_an_approval_opened(run: tuple[Path, Path, AccessGrants]) -> None:
    workspace, outside, grants = run
    grant_paths_once({"paths": [f"{outside}/a.csv"]}, policy=_POLICY, workspace_root=str(workspace), writable=False)
    assert reachable_access_roots() == grants.once != ()

    drop_once_grants()

    assert grants.once == ()
    assert reachable_access_roots() == ()


async def test_the_approval_node_closes_them_when_a_new_model_response_arrives(
    run: tuple[Path, Path, AccessGrants],
) -> None:
    workspace, outside, grants = run
    grant_paths_once({"paths": [f"{outside}/a.csv"]}, policy=_POLICY, workspace_root=str(workspace), writable=False)

    await ToolApprovalMiddleware().aafter_model({"messages": []}, None)

    assert grants.once == ()
