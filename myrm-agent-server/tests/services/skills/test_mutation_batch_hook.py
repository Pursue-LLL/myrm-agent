"""ServerSkillManageBatchHook fail-closed when skill_id cannot be resolved."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner import SkillBatchSnapshot


@pytest.mark.asyncio
async def test_hook_raises_when_skill_name_unresolved() -> None:
    from app.services.skills.mutation_batch_hook import ServerSkillManageBatchHook

    hook = ServerSkillManageBatchHook()
    snap = SkillBatchSnapshot(
        skill_name="missing-skill",
        skill_md="content",
        resources={},
        existed_before_batch=True,
    )
    session = AsyncMock()
    storage = MagicMock()
    storage._get_session = MagicMock(return_value=session)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.skill_optimization.bootstrap.get_skill_optimization_storage",
            return_value=storage,
        ),
        patch(
            "app.services.skills.write_orchestrator.resolve_skill_id_by_name",
            AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(RuntimeError, match="unresolved skill name"):
            await hook.on_batch_committed("batch-1", {"missing-skill": snap})
