"""The skill search tool keeps the language of the agent's prompt text when the bound set changes mid-session."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent._internals.skill_catalog_turn import deliver_bound_skills_catalog
from myrm_agent_harness.agent._internals.turn_history import TurnHistory
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from myrm_agent_harness.backends.skills.types import SkillMetadata

_CHINESE_MARKER = "技能库"
_ENGLISH_MARKER = "Search for missing capabilities"


class _Backend:
    def __init__(self, skills: list[SkillMetadata]) -> None:
        self.skills = skills

    async def list_skills(self) -> list[SkillMetadata]:
        return list(self.skills)


def _bulky_skills(count: int) -> list[SkillMetadata]:
    """Skills heavy enough that two dozen of them overflow the inline catalog budget, so the search tool mounts."""
    return [
        SkillMetadata(
            name=f"bound_{index:02d}_skill",
            description="detailed capability description " * 40,
            model_invocable=True,
            available=True,
        )
        for index in range(count)
    ]


async def _search_tool_description(config: AgentRuntimeConfig) -> str:
    agent = SkillAgent(llm=AsyncMock(), skill_backend=_Backend(_bulky_skills(25)), config=config)
    await deliver_bound_skills_catalog([HumanMessage(content="q")], agent, TurnHistory(mode="append"))
    mounted = {tool.name: tool for tool in agent._cached_tools or ()}
    assert "skill_search_tool" in mounted, "the bulky bound set no longer overflows the inline catalog budget"
    return mounted["skill_search_tool"].description


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "marker"),
    [
        pytest.param(AgentRuntimeConfig(locale="zh-CN"), _CHINESE_MARKER, id="ui-locale-chinese"),
        pytest.param(AgentRuntimeConfig(locale="en", prompt_locale="zh-CN"), _CHINESE_MARKER, id="prompt-locale-wins"),
        pytest.param(AgentRuntimeConfig(), _ENGLISH_MARKER, id="no-locale-is-english"),
    ],
)
async def test_a_resync_builds_the_search_tool_text_in_the_agents_prompt_language(
    config: AgentRuntimeConfig, marker: str
) -> None:
    assert marker in await _search_tool_description(config)
