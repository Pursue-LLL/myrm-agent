"""Delegated writers share the chat's workspace: delegation never clones, merges or deletes it.

Sub-agents run on their parent's executor, so every file tool of every child resolves against the one
workspace the parent run bound. A private copy promised to a child was never the one it wrote to, and the
cleanup of that copy removed the user's real workspace. The runs below are real ``BaseAgent.run`` calls
through ``delegate_task_tool`` and the real executor attempt; only the models are scripted and the child
agents are built by the test.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, tool

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegate_task_tool import create_delegate_task_tool
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, WorkspacePolicy
from myrm_agent_harness.core.context_vars import workspace_root_var
from tests.agent.middlewares.test_run_workspace import (
    _no_published_tools,  # noqa: F401  (autouse fixture of the shared workspace harness)
    _RecordingModel,
    _run,
    _Workspace,
)

_ORIGINAL = {"a.txt": "A-ORIGINAL", "b.txt": "B-ORIGINAL", "keep.txt": "USER FILE"}
_EDITED_A = "A-EDITED-BY-CHILD"
_EDITED_B = "B-EDITED-BY-CHILD"


@tool
async def edit_in_workspace_tool(name: str, content: str) -> str:
    """Edit a file in the workspace root the run is bound to (what a code or document tool does)."""
    (Path(str(workspace_root_var.get(None))) / name).write_text(content)
    return f"wrote {name}"


class _Catalog:
    async def resolve(self, type_id: str) -> SubagentConfig | None:
        return SubagentConfig(system_prompt="worker", timeout_seconds=60, max_retries=1, retry_backoff_seconds=0)

    async def list_available(self) -> list[str]:
        return ["worker"]


class _ChildBuilds:
    """What the executor handed ``build_child_agent`` for each child, in the order the children were built."""

    def __init__(self, children: list[BaseAgent]) -> None:
        self._children = deque(children)
        self.configs: list[SubagentConfig] = []
        self.tool_names: list[set[str]] = []

    async def __call__(
        self, config: SubagentConfig, tools: list[BaseTool], *args: object, **kwargs: object
    ) -> BaseAgent:
        self.configs.append(config)
        self.tool_names.append({registered.name for registered in tools})
        return self._children.popleft()


@pytest.fixture(autouse=True)
def scratch_tempdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where ``tempfile`` puts anything a run creates, so a leftover copy of the workspace is attributable."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.email=a@b.c", "-c", "user.name=test", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def _a_workspace(tmp_path: Path, *, git: bool) -> _Workspace:
    workspace = _Workspace(tmp_path)
    for name, content in _ORIGINAL.items():
        (workspace.path / name).write_text(content)
    if git:
        _git(workspace.path, "init", "-q")
        _git(workspace.path, "add", "-A")
        _git(workspace.path, "commit", "-q", "-m", "init")
    return workspace


def _a_child_that_edits(file_name: str, content: str, *, answer: str) -> _RecordingModel:
    edit = {
        "name": "edit_in_workspace_tool",
        "args": {"name": file_name, "content": content},
        "id": f"edit_{file_name}",
    }
    return _RecordingModel(responses=[AIMessage(content="", tool_calls=[edit]), AIMessage(content=answer)])


def _a_child_that_answers(answer: str) -> _RecordingModel:
    return _RecordingModel(responses=[AIMessage(content=answer)])


async def _delegate(
    workspace: _Workspace,
    delegation: dict[str, object],
    children: list[_RecordingModel],
    *,
    judge_replies: tuple[str, ...] = (),
) -> tuple[str, _ChildBuilds]:
    """Run a parent that makes one ``delegate_task_tool`` call; return what the parent model saw after it."""
    builds = _ChildBuilds([workspace.agent(model, [edit_in_workspace_tool]) for model in children])
    parent_model = _RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "delegate_task_tool", "args": delegation, "id": "call_delegate"}],
            ),
            *(AIMessage(content=reply) for reply in judge_replies),
            AIMessage(content="All sub-tasks finished."),
        ]
    )
    registry: list[BaseTool] = [edit_in_workspace_tool, create_file_write_tool()]
    parent = workspace.agent(parent_model, [edit_in_workspace_tool])
    parent.add_tools([create_delegate_task_tool(parent, lambda: registry, _Catalog())])

    with patch("myrm_agent_harness.agent.sub_agents.executor_attempt_mixin.build_child_agent", builds):
        await _run(parent, "Update the files with sub-agents.", workspace)

    return parent_model.requests[-1], builds


def _batch_of_two_writers() -> dict[str, object]:
    return {
        "mode": "batch",
        "wait": True,
        "max_concurrent": 2,
        "tasks": [
            {"agent_type": "worker", "objective": "update a.txt"},
            {"agent_type": "worker", "objective": "update b.txt"},
        ],
    }


def _assert_nothing_left_behind(workspace: _Workspace, scratch: Path, *, git: bool) -> None:
    assert not list(scratch.glob("subagent_ws_*")), "a run left a copy of the workspace behind"
    if not git:
        return
    branches = _git(workspace.path, "branch", "--list").replace("*", "").split()
    assert not [name for name in branches if name.startswith("myrm-subagent/")]
    assert len(_git(workspace.path, "worktree", "list").splitlines()) == 1
    assert not (workspace.path / ".worktrees").exists()
    assert not (workspace.path / ".gitignore").exists()


@pytest.mark.parametrize("git", [False, True], ids=["plain-directory", "git-repository"])
async def test_parallel_writers_edit_the_workspace_itself_and_leave_nothing_behind(
    tmp_path: Path, scratch_tempdir: Path, git: bool
) -> None:
    workspace = _a_workspace(tmp_path, git=git)
    children = [
        _a_child_that_edits("a.txt", _EDITED_A, answer="done A"),
        _a_child_that_edits("b.txt", _EDITED_B, answer="done B"),
    ]

    seen, builds = await _delegate(workspace, _batch_of_two_writers(), children)

    assert workspace.path.is_dir()
    assert (workspace.path / "a.txt").read_text() == _EDITED_A
    assert (workspace.path / "b.txt").read_text() == _EDITED_B
    assert (workspace.path / "keep.txt").read_text() == _ORIGINAL["keep.txt"]
    assert "done A" in seen and "done B" in seen
    assert "workspace_merge" not in seen
    assert {config.workspace_policy for config in builds.configs} == {WorkspacePolicy.INHERIT}
    _assert_nothing_left_behind(workspace, scratch_tempdir, git=git)


@pytest.mark.parametrize("git", [False, True], ids=["plain-directory", "git-repository"])
async def test_alternatives_are_read_only_candidates_and_leave_the_workspace_untouched(
    tmp_path: Path, scratch_tempdir: Path, git: bool
) -> None:
    workspace = _a_workspace(tmp_path, git=git)
    delegation = {
        "mode": "alternatives",
        "objective": "propose new text for a.txt",
        "expert_agent_types": ["worker", "worker"],
    }

    seen, builds = await _delegate(
        workspace, delegation, [_a_child_that_answers("CANDIDATE-ONE"), _a_child_that_answers("CANDIDATE-TWO")]
    )

    assert "CANDIDATE-ONE" in seen and "CANDIDATE-TWO" in seen
    assert {config.workspace_policy for config in builds.configs} == {WorkspacePolicy.READ_ONLY_SANDBOX}
    assert all("file_write_tool" not in names for names in builds.tool_names)
    assert {name: (workspace.path / name).read_text() for name in _ORIGINAL} == _ORIGINAL
    assert (workspace.path / ".git").is_dir() is git
    _assert_nothing_left_behind(workspace, scratch_tempdir, git=git)


def _contestant_folder(briefing: str) -> str:
    match = re.search(r"only inside the folder (contestant_\d+)/", briefing)
    assert match is not None, briefing
    return match.group(1)


async def test_a_tournament_keeps_the_workspace_and_tells_its_contestants_the_truth(
    tmp_path: Path, scratch_tempdir: Path
) -> None:
    workspace = _a_workspace(tmp_path, git=False)
    contestants = [
        _a_child_that_edits("a.txt", _EDITED_A, answer="done A"),
        _a_child_that_edits("b.txt", _EDITED_B, answer="done B"),
    ]
    delegation = {**_batch_of_two_writers(), "tournament": True}

    seen, _ = await _delegate(workspace, delegation, contestants, judge_replies=("A",))

    assert workspace.path.is_dir()
    assert (workspace.path / "keep.txt").read_text() == _ORIGINAL["keep.txt"]
    assert "tournament_winner" in seen and "workspace_merge" not in seen
    briefings = [contestant.requests[0] for contestant in contestants]
    assert all("TOURNAMENT MODE ACTIVE" in briefing and "discarded" not in briefing for briefing in briefings)
    assert {_contestant_folder(briefing) for briefing in briefings} == {"contestant_1", "contestant_2"}
    _assert_nothing_left_behind(workspace, scratch_tempdir, git=False)


async def test_a_race_keeps_the_workspace_and_returns_the_first_winner(tmp_path: Path, scratch_tempdir: Path) -> None:
    workspace = _a_workspace(tmp_path, git=False)
    racers = [
        _a_child_that_edits("a.txt", _EDITED_A, answer="done A"),
        _a_child_that_edits("b.txt", _EDITED_B, answer="done B"),
    ]
    delegation = {**_batch_of_two_writers(), "race": True}

    seen, _ = await _delegate(workspace, delegation, racers)

    assert workspace.path.is_dir()
    assert (workspace.path / "keep.txt").read_text() == _ORIGINAL["keep.txt"]
    assert "race_winner" in seen and "workspace_merge" not in seen and "race_merge" not in seen
    _assert_nothing_left_behind(workspace, scratch_tempdir, git=False)


def test_a_subagent_workspace_policy_never_promises_a_private_copy() -> None:
    """Children share their parent's executor binding, so the only policies are the two that are true."""
    assert {policy.value for policy in WorkspacePolicy} == {"inherit", "read_only_sandbox"}
