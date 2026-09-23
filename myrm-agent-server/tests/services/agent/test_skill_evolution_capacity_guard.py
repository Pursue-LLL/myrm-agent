"""Unit tests for Skill Evolution Capacity Guard in server layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.evolution import (
    BudgetStatus,
    EvolutionType,
    SkillBudgetConfig,
    SkillBudgetGovernor,
)

from app.core.types import ModelConfig
from app.services.agent.evolution.engine import (
    check_skill_budget_before_evolution,
    trigger_skill_evolution,
)


@pytest.fixture
def mock_model_cfg() -> MagicMock:
    cfg = MagicMock()
    cfg.provider = "anthropic"
    cfg.model = "claude-3-7-sonnet-20250219"
    return cfg


def test_check_skill_budget_before_evolution_allows_when_healthy() -> None:
    mock_store = MagicMock()
    mock_skill1 = MagicMock(content="a" * 400)
    mock_skill2 = MagicMock(content="b" * 400)
    mock_store.get_active_skills.return_value = [mock_skill1, mock_skill2]

    with patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=mock_store):
        config = SkillBudgetConfig(max_tokens=10_000, max_skill_count=10)
        res = check_skill_budget_before_evolution(
            agent_id="agent-1",
            evolution_type=EvolutionType.CAPTURED,
            governor=SkillBudgetGovernor(config),
        )
        assert res.allowed is True
        assert res.status == BudgetStatus.NORMAL
        assert res.current_count == 2


def test_trigger_skill_evolution_blocks_at_hard_limit(mock_model_cfg: ModelConfig) -> None:
    mock_store = MagicMock()
    mock_skills = [MagicMock(content="a" * 4000) for _ in range(12)]
    mock_store.get_active_skills.return_value = mock_skills

    config = SkillBudgetConfig(max_tokens=5_000, max_skill_count=10)
    governor = SkillBudgetGovernor(config)

    with (
        patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=mock_store),
        patch("app.services.skills.ws_hub.broadcast_message", new_callable=AsyncMock) as mock_broadcast,
        patch("asyncio.create_task") as mock_create_task,
    ):
        trigger_skill_evolution(
            chat_id="chat-bloat-test",
            model_cfg=mock_model_cfg,
            tool_steps_count=5,
            governor=governor,
        )

        # Evolution task should NOT be scheduled
        # create_task is called for broadcast_message, but not _run_evolution_task
        assert not any(
            getattr(call.args[0], "__name__", "") == "_run_evolution_task"
            for call in mock_create_task.call_args_list
            if call.args
        )
        assert mock_broadcast is not None


@pytest.mark.asyncio
async def test_trigger_skill_evolution_soft_limit_broadcasts_and_proceeds(mock_model_cfg: MagicMock) -> None:
    mock_store = MagicMock()
    mock_skills = [MagicMock(content="a" * 800) for _ in range(10)]
    mock_store.get_active_skills.return_value = mock_skills

    # 10 * 200 = 2000 tokens. With max_tokens = 3000 and soft ratio 0.8, soft limit is 2400.
    # Projected tokens = 2000 + 500 = 2500, which hits SOFT_LIMIT (2400 <= 2500 < 3000).
    config = SkillBudgetConfig(max_tokens=3_000, soft_limit_ratio=0.8, max_skill_count=20)
    governor = SkillBudgetGovernor(config)

    with (
        patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=mock_store),
        patch("app.services.skills.ws_hub.broadcast_message", new_callable=AsyncMock) as mock_broadcast,
        patch("app.services.agent.evolution.engine._run_evolution_task", new_callable=AsyncMock) as mock_run_task,
    ):
        trigger_skill_evolution(
            chat_id="chat-soft-test",
            model_cfg=mock_model_cfg,
            tool_steps_count=5,
            governor=governor,
        )

        # Soft limit allows execution to proceed
        mock_run_task.assert_called_once()
        assert mock_broadcast is not None
