"""``create_skill_agent`` starts the executor's background warm-up before it assembles the agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.types import AgentRuntimeSpec


def _spec() -> AgentRuntimeSpec:
    return AgentRuntimeSpec(agent_id="agent-warm-up", name="warm-up", system_prompt="test")


@pytest.mark.asyncio
async def test_create_skill_agent_warms_up_the_executor_once() -> None:
    from myrm_agent_harness.agent._factory.builder import create_skill_agent

    executor = MagicMock()

    with patch("myrm_agent_harness.agent.skill_agent.SkillAgent") as skill_agent_cls:
        skill_agent_cls.return_value = MagicMock()
        await create_skill_agent(spec=_spec(), llm=MagicMock(), executor=executor)

    executor.warm_up.assert_called_once_with()
    assert skill_agent_cls.call_args.kwargs["executor"] is executor


@pytest.mark.asyncio
async def test_create_skill_agent_without_an_executor_has_nothing_to_warm() -> None:
    from myrm_agent_harness.agent._factory.builder import create_skill_agent

    with patch("myrm_agent_harness.agent.skill_agent.SkillAgent") as skill_agent_cls:
        skill_agent_cls.return_value = MagicMock()
        await create_skill_agent(spec=_spec(), llm=MagicMock())

    assert skill_agent_cls.call_args.kwargs["executor"] is None
