"""Consecutive unattended goal turns of a chat must resolve to one cached execution unit."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.types.business import ModelConfig
from app.services.agent.execution_cache import compute_execution_fingerprint
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.unattended import trigger
from app.services.agent.goals.unattended.trigger import GoalStreamAgentContext, trigger_goal_stream

_MODEL_CFG = ModelConfig(model="gpt-4o", api_key="test-key")


def _user_configs() -> UserConfigs:
    """A user with no saved security config, as a fresh read of the store returns it."""
    return UserConfigs(
        model_cfg=_MODEL_CFG,
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict=None,
        personal_settings_dict={},
        mcp_dict=None,
        providers_dict={},
    )


async def _settled(captured: list[GeneralAgentParams], chat_id: str, expected: int) -> None:
    """Wait until the background goal task handed its params over and gave the chat session back."""
    for _ in range(200):
        if len(captured) == expected and not get_agent_gateway().is_session_active(chat_id):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"goal turn {expected} did not settle")


async def _trigger_goal_turns(
    chat_id: str, *, turns: int, agent_security_raw: dict[str, object] | None
) -> list[GeneralAgentParams]:
    """Trigger a goal ``turns`` times through the production trigger and return the params each trigger built.

    ``agent_security_raw`` is the security override of the agent profile the goal runs under.
    """
    goal = Goal(
        goal_id="g-cache-key",
        session_id=chat_id,
        objective="ship the weekly report",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=turns),
    )
    captured: list[GeneralAgentParams] = []

    async def capture_stream(params: GeneralAgentParams, **_kwargs: object) -> AsyncGenerator[object, None]:
        captured.append(params)
        if False:
            yield None

    # A clock that has moved on at every read, as triggers seconds apart see it.
    clock = SimpleNamespace(time=itertools.count(1_700_000_000.0, 30.0).__next__)
    agent_context = GoalStreamAgentContext(agent_security_raw=agent_security_raw)
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(side_effect=_user_configs)),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config", return_value=_MODEL_CFG),
        patch.object(trigger, "_resolve_goal_stream_agent_context", new=AsyncMock(return_value=agent_context)),
        patch("app.services.agent.streaming.ai_agent_service_stream", capture_stream),
        patch(
            "app.services.checkpoint.task_airbag_service.get_task_airbag_service",
            return_value=MagicMock(arm_airbag=AsyncMock()),
        ),
        patch("app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots", new=AsyncMock(return_value=[])),
        patch.object(trigger, "time", clock),
    ):
        for turn in range(1, turns + 1):
            await trigger_goal_stream(chat_id, goal)
            await _settled(captured, chat_id, turn)
    return captured


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_security_raw",
    [None, {"yoloModeEnabled": True, "yolo_mode_timeout": 600}],
    ids=["no-agent-yolo", "agent-yolo-timeout"],
)
async def test_consecutive_goal_turns_resolve_to_one_execution_unit(agent_security_raw: dict[str, object] | None) -> None:
    """The trigger forces YOLO on for the headless run and stamps the moment it did, so two turns of one goal
    differ in that stamp alone, and an agent's YOLO timeout counts from it. They must still share a cache key:
    otherwise every turn tears down the unit, and the browser session it holds, that the previous turn built."""
    chat_id = "chat-goal-cache-key"
    first, second = await _trigger_goal_turns(chat_id, turns=2, agent_security_raw=agent_security_raw)

    assert first.agent_security_raw == second.agent_security_raw == agent_security_raw
    assert first.security_config_raw is not None
    assert second.security_config_raw is not None
    assert first.security_config_raw["yolo_mode_enabled_at"] != second.security_config_raw["yolo_mode_enabled_at"]

    def goal_turn_fingerprint(params: GeneralAgentParams) -> str:
        return compute_execution_fingerprint(AgentFactory.create_general_agent(params), has_active_goal=True)

    assert goal_turn_fingerprint(first) == goal_turn_fingerprint(second)
