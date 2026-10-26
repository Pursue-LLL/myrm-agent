"""Contract: which side-effecting tools a delegated child holds.

A child receives the parent's own tool objects, so a tool bound to the parent's state or reaching beyond a
read-only child's workspace must be stripped by ``filter_tools``. Every tool the safety table does not mark
read-only is classified below with the mechanism that decides it. A new tool fails
``test_every_side_effecting_tool_is_classified`` until it is classified, and the real ``filter_tools`` must
then agree with the classification.
"""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.sub_agents.builder import filter_tools
from myrm_agent_harness.agent.sub_agents.spawn_prep import apply_readonly_to_config
from myrm_agent_harness.agent.sub_agents.strategic_advisor_schema import READONLY_FORBIDDEN_TOOLS
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, WorkspacePolicy
from myrm_agent_harness.core.security.tool_registry import (
    PARENT_BOUND_WRITER_TOOLS,
    TOOL_GROUP_MAP,
    TOOL_SAFETY_METADATA,
)


class Disposition(StrEnum):
    BLOCKED_FOR_EVERY_CHILD = "blocked for every child (manifest leaf_blocked_tools)"
    BLOCKED_FOR_READ_ONLY_CHILD = "kept by a normal child, stripped from a read-only child"
    KEPT = "kept by every child"


class Mechanism(StrEnum):
    RUN_STATE = "writes the plan file, goal or kanban board the parent run owns"
    PARENT_BOUND_STORE = "bound to the parent's memory manager or scheduler"
    DELEGATION = "spawns or messages other agents; a child is a leaf"
    SKILL_LIBRARY = "mutates the shared skill library"
    WORKSPACE_WRITE = "writes the workspace"
    EXTERNAL_AGENT = "starts an external agent session"
    KNOWLEDGE_STORE = "writes the shared knowledge store"
    PARENT_SESSION = "acts on the parent run's live browser session, gated per call by the permission engine"
    PERMISSION_GATED = "gated per call by the permission engine"
    JOB_CONTROL = "acts only on processes that already exist, and checks the EXECUTE capability itself"


_EVERY = Disposition.BLOCKED_FOR_EVERY_CHILD
_READ_ONLY = Disposition.BLOCKED_FOR_READ_ONLY_CHILD
_KEPT = Disposition.KEPT

_CLASSIFICATION: dict[str, tuple[Disposition, Mechanism]] = {
    "complete_goal_tool": (_EVERY, Mechanism.RUN_STATE),
    "todo_write": (_EVERY, Mechanism.RUN_STATE),
    "kanban_add_task": (_EVERY, Mechanism.RUN_STATE),
    "kanban_attach": (_EVERY, Mechanism.RUN_STATE),
    "kanban_block": (_EVERY, Mechanism.RUN_STATE),
    "kanban_cancel_task": (_EVERY, Mechanism.RUN_STATE),
    "kanban_comment": (_EVERY, Mechanism.RUN_STATE),
    "kanban_complete": (_EVERY, Mechanism.RUN_STATE),
    "kanban_heartbeat": (_EVERY, Mechanism.RUN_STATE),
    "kanban_retry_task": (_EVERY, Mechanism.RUN_STATE),
    "kanban_revise_plan": (_EVERY, Mechanism.RUN_STATE),
    "kanban_unblock": (_EVERY, Mechanism.RUN_STATE),
    "cron_manage_tool": (_EVERY, Mechanism.PARENT_BOUND_STORE),
    "memory_manage_tool": (_EVERY, Mechanism.PARENT_BOUND_STORE),
    "memory_save_tool": (_EVERY, Mechanism.PARENT_BOUND_STORE),
    "delegate_task_tool": (_EVERY, Mechanism.DELEGATION),
    "send_teammate_message_tool": (_EVERY, Mechanism.DELEGATION),
    "subagent_control_tool": (_EVERY, Mechanism.DELEGATION),
    "skill_manage_tool": (_EVERY, Mechanism.SKILL_LIBRARY),
    "bash_code_execute_tool": (_READ_ONLY, Mechanism.WORKSPACE_WRITE),
    "file_edit_tool": (_READ_ONLY, Mechanism.WORKSPACE_WRITE),
    "file_write_tool": (_READ_ONLY, Mechanism.WORKSPACE_WRITE),
    "invoke_acp_agent_tool": (_READ_ONLY, Mechanism.EXTERNAL_AGENT),
    "wiki_apply_tool": (_READ_ONLY, Mechanism.KNOWLEDGE_STORE),
    "wiki_ingest_tool": (_READ_ONLY, Mechanism.KNOWLEDGE_STORE),
    "browser_execute_script_tool": (_KEPT, Mechanism.PARENT_SESSION),
    "browser_interact_tool": (_KEPT, Mechanism.PARENT_SESSION),
    "browser_manage_tool": (_KEPT, Mechanism.PARENT_SESSION),
    "browser_navigate_tool": (_KEPT, Mechanism.PARENT_SESSION),
    "desktop_interact_tool": (_KEPT, Mechanism.PERMISSION_GATED),
    "desktop_vision_tool": (_KEPT, Mechanism.PERMISSION_GATED),
    "bash_process_tool": (_KEPT, Mechanism.JOB_CONTROL),
}

_NORMAL_CHILD = SubagentConfig(system_prompt="child")
_READ_ONLY_CHILD = apply_readonly_to_config(_NORMAL_CHILD, True)
_SANDBOX_ONLY_CHILD = replace(_NORMAL_CHILD, workspace_policy=WorkspacePolicy.READ_ONLY_SANDBOX)


def _held(config: SubagentConfig, *names: str) -> set[str]:
    """Names of ``names`` that survive ``filter_tools`` for ``config``."""
    tools = []
    for name in names:
        tool = MagicMock()
        tool.name = name
        tools.append(tool)
    return {tool.name for tool in filter_tools(config, tools)}


def test_every_side_effecting_tool_is_classified() -> None:
    side_effecting = {name for name, meta in TOOL_SAFETY_METADATA.items() if not meta.is_read_only}

    assert side_effecting == set(_CLASSIFICATION), (
        f"unclassified: {sorted(side_effecting - set(_CLASSIFICATION))}; "
        f"no longer side-effecting: {sorted(set(_CLASSIFICATION) - side_effecting)}"
    )


@pytest.mark.parametrize(
    ("name", "disposition"),
    [(name, disposition) for name, (disposition, _) in _CLASSIFICATION.items()],
)
def test_filter_tools_agrees_with_classification(name: str, disposition: Disposition) -> None:
    expected_normal, expected_read_only = {
        Disposition.BLOCKED_FOR_EVERY_CHILD: (False, False),
        Disposition.BLOCKED_FOR_READ_ONLY_CHILD: (True, False),
        Disposition.KEPT: (True, True),
    }[disposition]

    assert (name in _held(_NORMAL_CHILD, name), name in _held(_READ_ONLY_CHILD, name)) == (
        expected_normal,
        expected_read_only,
    )


def test_parent_bound_writers_are_exactly_the_run_state_tools() -> None:
    run_state = {name for name, (_, mechanism) in _CLASSIFICATION.items() if mechanism is Mechanism.RUN_STATE}

    assert run_state == PARENT_BOUND_WRITER_TOOLS


def test_read_only_members_of_parent_bound_groups_stay_available() -> None:
    readers = {
        name
        for group in ("planning", "kanban")
        for name in TOOL_GROUP_MAP[group]
        if TOOL_SAFETY_METADATA[name].is_read_only
    }

    assert readers == {"kanban_show", "kanban_list_tasks"}
    assert _held(_NORMAL_CHILD, *readers) == readers


def test_declared_read_only_forbidden_tools_never_reach_a_read_only_child() -> None:
    assert _held(_READ_ONLY_CHILD, *READONLY_FORBIDDEN_TOOLS) == set()


def test_sandbox_policy_alone_strips_tools_that_escape_the_workspace() -> None:
    escaping = {
        name
        for name, (_, mechanism) in _CLASSIFICATION.items()
        if mechanism in (Mechanism.EXTERNAL_AGENT, Mechanism.KNOWLEDGE_STORE)
    }

    assert escaping == {"invoke_acp_agent_tool", "wiki_apply_tool", "wiki_ingest_tool"}
    assert _held(_SANDBOX_ONLY_CHILD, *escaping) == set()
