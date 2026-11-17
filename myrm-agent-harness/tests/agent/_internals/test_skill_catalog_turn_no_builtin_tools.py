"""A model without built-in tools is sent no skill catalog and has no skill index kept for it.

The catalog sends the model to ``skill_select_tool`` and ``skill_search_tool``, which an agent running with
``no_builtin_tools`` does not have. The turn still records which skills were bound, for the turn receipt.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from myrm_agent_harness.agent._internals.skill_catalog_turn import (
    CatalogDelivery,
    deliver_bound_skills_catalog,
    sync_bound_skills_for_resume,
)
from myrm_agent_harness.agent._internals.turn_history import TurnHistory
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.skill_agent.context import get_bound_skills_receipt, reset_bound_skills_receipt
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from myrm_agent_harness.backends.skills.types import SkillMetadata

# Heavy enough that a couple of dozen overflow the inline catalog budget, so the ``skill_search`` index is in play too.
_SKILLS = [
    SkillMetadata(
        name=f"bound_{index:02d}_skill",
        description="detailed capability description " * 40,
        model_invocable=True,
        available=True,
    )
    for index in range(30)
]
_BOUND_NAMES = sorted(skill.name for skill in _SKILLS)


@pytest.fixture(autouse=True)
def _clean_receipt() -> Iterator[None]:
    reset_bound_skills_receipt()
    yield
    reset_bound_skills_receipt()


def _agent(*, no_builtin_tools: bool) -> SkillAgent:
    backend = AsyncMock()
    backend.list_skills = AsyncMock(return_value=_SKILLS)
    return SkillAgent(
        llm=AsyncMock(), skill_backend=backend, config=AgentRuntimeConfig(no_builtin_tools=no_builtin_tools)
    )


def _receipt_names() -> list[str]:
    return sorted(skill.name for skill in get_bound_skills_receipt())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_builtin_tools", "action", "catalog_sent"),
    [(False, "baseline", True), (True, "none", False)],
    ids=["built-in-tools", "no-built-in-tools"],
)
async def test_a_rebuilt_conversation_is_sent_the_catalog_only_when_the_model_can_load_skills(
    no_builtin_tools: bool, action: str, catalog_sent: bool
) -> None:
    agent = _agent(no_builtin_tools=no_builtin_tools)
    messages: list[BaseMessage] = [HumanMessage(content="hello")]

    delivery = await deliver_bound_skills_catalog(messages, agent, TurnHistory(mode="replace"))

    assert delivery.action == action
    assert ("<bound_skills" in str(messages[0].content)) is catalog_sent
    assert (agent._synced_skill_fingerprint is not None) is catalog_sent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_builtin_tools", "action", "catalog_sent"),
    [(False, "update", True), (True, "none", False)],
    ids=["built-in-tools", "no-built-in-tools"],
)
async def test_a_continued_thread_is_sent_a_catalog_update_only_when_the_model_can_load_skills(
    no_builtin_tools: bool, action: str, catalog_sent: bool
) -> None:
    agent = _agent(no_builtin_tools=no_builtin_tools)
    messages: list[BaseMessage] = [HumanMessage(content="two")]
    history = TurnHistory(mode="continue", thread_messages=(HumanMessage(content="one"), AIMessage(content="ok")))

    delivery = await deliver_bound_skills_catalog(messages, agent, history)

    assert delivery.action == action
    assert ("<bound_skills" in str(messages[0].content)) is catalog_sent


@pytest.mark.asyncio
async def test_a_turn_without_built_in_tools_reports_no_catalog_step_and_leaves_the_messages_alone() -> None:
    agent = _agent(no_builtin_tools=True)
    messages: list[BaseMessage] = [HumanMessage(content="hello")]

    delivery = await deliver_bound_skills_catalog(messages, agent, TurnHistory(mode="replace"))

    assert delivery == CatalogDelivery(action="none")
    assert delivery.telemetry() == {"catalog_delivery": "none"}
    assert [message.content for message in messages] == ["hello"]


@pytest.mark.asyncio
@pytest.mark.parametrize("no_builtin_tools", [False, True], ids=["built-in-tools", "no-built-in-tools"])
async def test_the_turn_receipt_names_the_bound_skills_either_way(no_builtin_tools: bool) -> None:
    agent = _agent(no_builtin_tools=no_builtin_tools)

    await deliver_bound_skills_catalog([HumanMessage(content="hello")], agent, TurnHistory(mode="replace"))

    assert _receipt_names() == _BOUND_NAMES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_builtin_tools", "index_synced"), [(False, True), (True, False)], ids=["built-in-tools", "no-built-in-tools"]
)
async def test_a_resume_keeps_the_skill_index_only_for_a_model_that_can_search_skills(
    no_builtin_tools: bool, index_synced: bool
) -> None:
    agent = _agent(no_builtin_tools=no_builtin_tools)

    await sync_bound_skills_for_resume(agent)

    assert (agent._synced_skill_fingerprint is not None) is index_synced
    assert _receipt_names() == _BOUND_NAMES
