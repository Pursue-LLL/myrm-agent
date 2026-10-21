"""ServerSkillManageBatchHook persists all snapshots in one transaction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner import SkillBatchSnapshot


@pytest.mark.asyncio
async def test_hook_commits_once_for_multiple_skills() -> None:
    from app.services.skills.mutation_batch_hook import ServerSkillManageBatchHook

    hook = ServerSkillManageBatchHook()
    snaps = {
        "skill-a": SkillBatchSnapshot(
            skill_name="skill-a",
            skill_md="a",
            resources={},
            existed_before_batch=True,
        ),
        "skill-b": SkillBatchSnapshot(
            skill_name="skill-b",
            skill_md="b",
            resources={},
            existed_before_batch=True,
        ),
    }
    session = AsyncMock()
    storage = MagicMock()
    storage._get_session = MagicMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    insert = AsyncMock()
    service = MagicMock()
    service.insert_mutation_batch_snapshot = insert

    with (
        patch(
            "app.services.skill_optimization.bootstrap.get_skill_optimization_storage",
            return_value=storage,
        ),
        patch(
            "app.services.skills.write_orchestrator.resolve_skill_id_by_name",
            AsyncMock(side_effect=["id-a", "id-b"]),
        ),
        patch(
            "app.services.skill_optimization.rollback_service.RollbackService",
            return_value=service,
        ),
    ):
        await hook.on_batch_committed("batch-1", snaps)

    assert insert.await_count == 2
    assert all(call.kwargs.get("commit") is False for call in insert.await_args_list)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_hook_rolls_back_session_when_second_skill_unresolved() -> None:
    from app.services.skills.mutation_batch_hook import ServerSkillManageBatchHook

    hook = ServerSkillManageBatchHook()
    snaps = {
        "skill-a": SkillBatchSnapshot(
            skill_name="skill-a",
            skill_md="a",
            resources={},
            existed_before_batch=True,
        ),
        "skill-b": SkillBatchSnapshot(
            skill_name="skill-b",
            skill_md="b",
            resources={},
            existed_before_batch=True,
        ),
    }
    session = AsyncMock()
    storage = MagicMock()
    storage._get_session = MagicMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    insert = AsyncMock()
    service = MagicMock()
    service.insert_mutation_batch_snapshot = insert

    with (
        patch(
            "app.services.skill_optimization.bootstrap.get_skill_optimization_storage",
            return_value=storage,
        ),
        patch(
            "app.services.skills.write_orchestrator.resolve_skill_id_by_name",
            AsyncMock(side_effect=["id-a", None]),
        ),
        patch(
            "app.services.skill_optimization.rollback_service.RollbackService",
            return_value=service,
        ),
    ):
        with pytest.raises(RuntimeError, match="unresolved skill name"):
            await hook.on_batch_committed("batch-1", snaps)

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
