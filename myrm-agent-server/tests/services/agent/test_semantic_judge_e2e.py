"""End-to-end integration test for Semantic Completion Judge.

Uses a real LLM (via litellm) — NO mocks.
Requires WebUI model config (patched from BASIC_* in .env.test).
"""

import os

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.agent.goals.audit import build_judge_criteria
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus

from app.core.types import ModelConfig
from app.services.agent.goal_registry import ServerGoalManager, _parse_judge_json

load_dotenv(override=False)


def _platform_model_from_env() -> ModelConfig:
    from myrm_agent_harness.agent.config.litellm_routing import (
        normalize_env_model_selection_string,
    )

    raw_model = os.environ.get("LITE_MODEL") or os.environ.get("BASIC_MODEL")
    if not raw_model:
        raise RuntimeError("E2E test requires LITE_MODEL or BASIC_MODEL in .env.test")

    api_key = os.environ.get("LITE_API_KEY") or os.environ.get("BASIC_API_KEY")
    base_url = os.environ.get("LITE_BASE_URL") or os.environ.get("BASIC_BASE_URL")
    if not api_key:
        raise RuntimeError("E2E test requires LITE_API_KEY or BASIC_API_KEY in .env.test")

    return ModelConfig(
        model=normalize_env_model_selection_string(raw_model),
        api_key=api_key,
        base_url=base_url or None,
    )


@pytest.fixture
def manager():
    from unittest.mock import AsyncMock

    return ServerGoalManager(AsyncMock())


def _make_goal(objective: str, turns: int = 3, max_turns: int = 20) -> Goal:
    return Goal(
        goal_id="e2e-test-goal",
        session_id="e2e-test-session",
        objective=objective,
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=max_turns),
        turns_used=turns,
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY",
)
class TestSemanticJudgeE2E:
    """Real LLM semantic judge integration tests."""

    @pytest.mark.asyncio
    async def test_obvious_completion(self, manager: ServerGoalManager):
        """Agent clearly states the task is done — judge should return done=True."""
        from unittest.mock import AsyncMock, patch

        goal = _make_goal("Summarize the main benefits of Python")
        criteria = build_judge_criteria(goal)

        agent_response = (
            "Here is the summary of Python's main benefits:\n\n"
            "1. Easy to learn and readable syntax\n"
            "2. Large standard library and ecosystem\n"
            "3. Cross-platform compatibility\n"
            "4. Strong community support\n\n"
            "The summary is complete and covers all key points."
        )

        model_cfg = _platform_model_from_env()
        with patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new=AsyncMock(
                return_value={
                    "model": model_cfg.model,
                    "api_key": model_cfg.api_key,
                    **({"api_base": model_cfg.base_url} if model_cfg.base_url else {}),
                }
            ),
        ):
            result = await manager.evaluate_semantic(criteria, agent_response)

        assert result.passed is True, f"Expected passed=True, got reason: {result.reason}"

    @pytest.mark.asyncio
    async def test_obvious_incompletion(self, manager: ServerGoalManager):
        """Agent is clearly still working — judge should return done=False."""
        from unittest.mock import AsyncMock, patch

        goal = _make_goal("Research and write a comprehensive report on quantum computing")
        criteria = build_judge_criteria(goal)

        agent_response = (
            "I'm starting to research quantum computing. "
            "Let me search for the latest developments first. "
            "I'll need to cover several topics including qubits, "
            "quantum gates, and current applications."
        )

        model_cfg = _platform_model_from_env()
        with patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new=AsyncMock(
                return_value={
                    "model": model_cfg.model,
                    "api_key": model_cfg.api_key,
                    **({"api_base": model_cfg.base_url} if model_cfg.base_url else {}),
                }
            ),
        ):
            result = await manager.evaluate_semantic(criteria, agent_response)

        assert result.passed is False, f"Expected passed=False, got reason: {result.reason}"

    @pytest.mark.asyncio
    async def test_criteria_structure(self):
        """Verify build_judge_criteria produces well-formed prompt."""
        goal = _make_goal("Fix the login bug", turns=5, max_turns=10)
        criteria = build_judge_criteria(goal)

        assert "Fix the login bug" in criteria
        assert "done" in criteria.lower()
        assert "reason" in criteria.lower()
        assert "JSON" in criteria

    @pytest.mark.asyncio
    async def test_parse_judge_json_real_world_formats(self):
        """Validate parsing logic against formats LLMs actually produce."""
        cases = [
            ('{"done": true, "reason": "Task completed"}', True),
            ('{"done": false, "reason": "Still working"}', False),
            ('```json\n{"done": true, "reason": "All done"}\n```', True),
            ('Based on analysis: {"done": false, "reason": "Needs more work"}', False),
            ('{"done": "True", "reason": "Completed"}', True),
            ('{"done": "false", "reason": "Not yet"}', False),
        ]

        for raw, expected_done in cases:
            parsed = _parse_judge_json(raw)
            assert parsed is not None, f"Failed to parse: {raw!r}"
            assert parsed["done"] is expected_done, (
                f"Expected done={expected_done} for {raw!r}, got {parsed['done']}"
            )
