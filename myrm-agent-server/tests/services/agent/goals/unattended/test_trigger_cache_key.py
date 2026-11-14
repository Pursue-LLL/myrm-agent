"""Consecutive unattended goal turns of a chat must resolve to one cached execution unit."""

from __future__ import annotations

import pytest

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.services.agent.execution_cache import compute_execution_fingerprint

from .trigger_testkit import trigger_goal_turns


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
    first, second = await trigger_goal_turns(chat_id, turns=2, agent_security_raw=agent_security_raw)

    assert first.agent_security_raw == second.agent_security_raw == agent_security_raw
    assert first.security_config_raw is not None
    assert second.security_config_raw is not None
    assert first.security_config_raw["yolo_mode_enabled_at"] != second.security_config_raw["yolo_mode_enabled_at"]

    def goal_turn_fingerprint(params: GeneralAgentParams) -> str:
        return compute_execution_fingerprint(AgentFactory.create_general_agent(params), has_active_goal=True)

    assert goal_turn_fingerprint(first) == goal_turn_fingerprint(second)
