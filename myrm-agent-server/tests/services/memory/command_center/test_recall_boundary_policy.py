"""The recall boundary reports a manager's read scopes and write target as configured, with no display wording."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryWritePolicy

from app.schemas.memory.command_center import MemoryRecallBoundaryData, MemoryRecallScopeBoundary
from app.services.memory.command_center.command_center_recall_boundary import build_recall_boundary

_LEVELS = ["global", "agent", "channel", "conversation", "task", "shared"]


def _manager(policy: AgentMemoryPolicy | None) -> MagicMock:
    manager = MagicMock()
    manager.memory_policy = policy
    manager.count_memories = AsyncMock(return_value=0)
    manager.list_memories = AsyncMock(return_value=[])
    return manager


async def _boundary(policy: AgentMemoryPolicy | None, **identity: str) -> MemoryRecallBoundaryData:
    with patch(
        "app.services.memory.command_center.command_center_recall_boundary.build_candidate_records",
        new=AsyncMock(return_value=[]),
    ):
        return await build_recall_boundary(AsyncMock(), _manager(policy), **identity)


def _active(data: MemoryRecallBoundaryData) -> dict[str, bool]:
    return {scope.level: scope.is_active for scope in data.read_scopes}


@pytest.mark.asyncio
async def test_without_a_policy_every_level_is_readable_and_writes_inherit() -> None:
    data = await _boundary(None)

    assert [scope.level for scope in data.read_scopes] == _LEVELS
    assert all(scope.is_active for scope in data.read_scopes)
    assert data.write_policy == MemoryWritePolicy.INHERIT


@pytest.mark.asyncio
async def test_a_restricted_policy_marks_the_other_levels_restricted() -> None:
    data = await _boundary(AgentMemoryPolicy.preset_l2_flow(agent_id="a1", task_id="t1"))

    assert _active(data) == {
        "global": True,
        "agent": False,
        "channel": False,
        "conversation": False,
        "task": True,
        "shared": False,
    }
    assert data.write_policy == MemoryWritePolicy.TASK
    assert data.model_dump(mode="json")["write_policy"] == "task"
    assert data.agent_id == "a1"
    assert data.task_id == "t1"


@pytest.mark.asyncio
async def test_a_policy_that_names_no_read_scope_leaves_every_level_readable() -> None:
    data = await _boundary(AgentMemoryPolicy.preset_standard(agent_id="a1"))

    assert all(_active(data).values())
    assert data.write_policy == MemoryWritePolicy.INHERIT


@pytest.mark.asyncio
async def test_namespace_patterns_name_only_ids_that_exist() -> None:
    anonymous = {scope.level: scope.namespace_pattern for scope in (await _boundary(None)).read_scopes}
    identified = {
        scope.level: scope.namespace_pattern for scope in (await _boundary(None, agent_id="a1", task_id="t1")).read_scopes
    }

    # Without an agent id the harness reads the "default" agent namespace; a task namespace needs a task id.
    assert (anonymous["agent"], anonymous["task"]) == ("agent:default", "task:*")
    assert (identified["agent"], identified["task"]) == ("agent:a1", "task:t1")
    assert {level: identified[level] for level in ("global", "channel", "conversation", "shared")} == {
        "global": "global",
        "channel": "channel:*",
        "conversation": "conversation:*",
        "shared": "shared:*",
    }


def test_a_scope_level_carries_no_display_wording() -> None:
    """Labels and descriptions are localized by the client from the level, so the record holds none."""
    assert set(MemoryRecallScopeBoundary.model_fields) == {"level", "is_active", "namespace_pattern"}
