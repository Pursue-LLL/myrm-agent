"""Shared driver for the unattended-goal trigger tests.

Runs the production ``trigger_goal_stream`` against the real ``AgentGateway`` with only the agent stream, the model
resolution and the user-config read replaced, and hands back the ``GeneralAgentParams`` each trigger built.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus

from app.ai_agents.agents import GeneralAgentParams
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.types.business import ModelConfig
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.unattended import trigger
from app.services.agent.goals.unattended.trigger import GoalStreamAgentContext, trigger_goal_stream

MODEL_CFG = ModelConfig(model="gpt-4o", api_key="test-key")


def user_configs(security_config_dict: dict[str, object] | None = None) -> UserConfigs:
    """A user's configs as the store returns them; ``security_config_dict`` is the saved security config, if any."""
    return UserConfigs(
        model_cfg=MODEL_CFG,
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict=None,
        personal_settings_dict={},
        mcp_dict=None,
        providers_dict={},
        security_config_dict=security_config_dict,
    )


async def _settled(captured: list[GeneralAgentParams], chat_id: str, expected: int) -> None:
    """Wait until the background goal task handed its params over and gave the chat session back."""
    for _ in range(200):
        if len(captured) == expected and not get_agent_gateway().is_session_active(chat_id):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"goal turn {expected} did not settle")


async def trigger_goal_turns(
    chat_id: str,
    *,
    turns: int,
    agent_security_raw: dict[str, object] | None = None,
    configs: UserConfigs | None = None,
) -> list[GeneralAgentParams]:
    """Trigger a goal ``turns`` times through the production trigger and return the params each trigger built.

    ``agent_security_raw`` is the security override of the agent profile the goal runs under. ``configs`` is the one
    object every config read returns, as the loader's cache hands it out; by default each read is a fresh one that
    saved nothing.
    """
    goal = Goal(
        goal_id="g-trigger",
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
    load_configs = AsyncMock(side_effect=user_configs) if configs is None else AsyncMock(return_value=configs)
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=load_configs),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config", return_value=MODEL_CFG),
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
