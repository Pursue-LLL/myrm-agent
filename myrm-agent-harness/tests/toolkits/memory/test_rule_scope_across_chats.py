"""A rule belongs to the agent that wrote it: that agent's other chats follow it, whichever manager approved it, and no other agent does.

Real managers over one SQLite file, bound the way the server binds them: a chat's manager holds ``global``, its agent and
its conversation, and the settings inbox that approves queued proposals holds ``global`` and the default agent.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from myrm_agent_harness.agent._internals.memory_extraction import persist_extracted_memories
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.extractor.models import ExtractedMemory
from myrm_agent_harness.toolkits.memory.types import MemoryType, ProceduralMemory, RuleSource

NewManager = Callable[..., MemoryManager]

ACTION = "end every reply with the line - Quill"


def chat_manager(new_manager: NewManager, agent: str, chat: str, *, approval_required: bool = False) -> MemoryManager:
    return new_manager(
        ["global", f"agent:{agent}", f"conversation:{chat}"], agent_id=agent, approval_required=approval_required
    )


def settings_inbox(new_manager: NewManager) -> MemoryManager:
    return new_manager(["global", "agent:default"], approval_required=True)


async def rule_actions(manager: MemoryManager) -> list[str]:
    """The rules a chat of ``manager`` is given, as the prompt builder reads them."""
    context = await manager.get_context(include_profile=False, include_rules=True)
    rules = context["rules"]
    assert isinstance(rules, list)
    return [str(rule["action"]) for rule in rules]


async def test_a_rule_written_in_one_chat_follows_the_agent_into_its_other_chats(new_manager: NewManager) -> None:
    await chat_manager(new_manager, "x", "a").add_rule("always", ACTION, source=RuleSource.AGENT_SELF)

    assert await rule_actions(chat_manager(new_manager, "x", "b")) == [ACTION]
    assert await rule_actions(chat_manager(new_manager, "y", "b")) == []
    assert await rule_actions(chat_manager(new_manager, "default", "b")) == []


@pytest.mark.parametrize("agent", ["x", "default"])
async def test_an_approved_rule_stays_with_the_agent_that_proposed_it(new_manager: NewManager, agent: str) -> None:
    proposer = chat_manager(new_manager, agent, "a", approval_required=True)
    proposal = await proposer.add_rule("always", ACTION, source=RuleSource.AGENT_SELF, honor_approval=True)

    stored = await settings_inbox(new_manager).approve(str(proposal.metadata["_pending_id"]))

    assert isinstance(stored, ProceduralMemory)
    assert stored.scope.primary_namespace == f"agent:{agent}"
    assert stored.scope.namespaces == ["global", f"agent:{agent}"]
    assert await rule_actions(chat_manager(new_manager, agent, "b")) == [ACTION]
    others = {"x", "y", "default"} - {agent}
    for other in sorted(others):
        assert await rule_actions(chat_manager(new_manager, other, "b")) == []


async def test_a_proposal_queued_without_a_scope_takes_the_scope_of_the_manager_that_approves_it(
    new_manager: NewManager,
) -> None:
    rule = ProceduralMemory(content=f"When: always → Do: {ACTION}", trigger="always", action=ACTION)

    stored = await settings_inbox(new_manager).store(rule, _bypass_approval=True, _scope_prevalidated=True)

    assert isinstance(stored, ProceduralMemory)
    assert (stored.scope.primary_namespace, stored.scope.namespaces) == ("agent:default", ["global", "agent:default"])


async def test_an_approved_extracted_rule_stays_with_the_agent_whose_chat_it_came_from(new_manager: NewManager) -> None:
    proposer = chat_manager(new_manager, "x", "a")
    extracted = ExtractedMemory(
        memory_type=MemoryType.PROCEDURAL,
        content=f"Rule: {ACTION}",
        confidence=0.95,
        importance=0.8,
        trigger="always",
        action=ACTION,
    )
    await persist_extracted_memories([extracted], proposer, "chat-a")
    [queued] = await proposer.list_pending()

    stored = await settings_inbox(new_manager).approve(queued.id)

    assert isinstance(stored, ProceduralMemory)
    assert (stored.scope.primary_namespace, stored.scope.namespaces) == ("agent:x", ["global", "agent:x"])
    assert stored.scope.conversation_id is None
    assert await rule_actions(chat_manager(new_manager, "x", "b")) == [ACTION]
    assert await rule_actions(chat_manager(new_manager, "default", "b")) == []
