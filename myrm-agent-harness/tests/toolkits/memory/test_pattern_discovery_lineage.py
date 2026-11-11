"""A discovered pattern derives from the chats of every memory the model read, so deleting any of them removes it.

The model reads the newest memories the prompt lists and the consolidation insights it quotes; the pattern event and the
rule promoted from an established pattern record the chats of those and no others. Real manager over an embedded Qdrant
and SQLite; only the chat model is a stub.
"""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.bookkeeping import write_bookkeeping
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_INSIGHT_TAG
from myrm_agent_harness.toolkits.memory.strategies.lineage import chat_links
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    _PROFILE_KEY_CONSOLIDATION_COUNT,
    run_pattern_discovery,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_models import (
    DiscoveredPattern,
    PatternDiscoveryResponse,
    PatternDurability,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_prompts import MAX_PROMPT_MEMORIES
from myrm_agent_harness.toolkits.memory.types import AnyMemory, EpisodicMemory, MemoryType, ProceduralMemory
from tests.support.consolidation_seeds import NewManager, seed, semantic

# More memories than the prompt lists, so some are read by the model and some are not.
MEMORIES = MAX_PROMPT_MEMORIES + 30


def chat(index: int) -> str:
    return f"chat-{index:03d}"


def established_habit() -> PatternDiscoveryResponse:
    return PatternDiscoveryResponse(
        patterns=[
            DiscoveredPattern(
                title="spreadsheet habit",
                description="the user asks for spreadsheets",
                evidence_summary="seen in many chats",
                durability=PatternDurability.ESTABLISHED,
                confidence=0.9,
                actionable_suggestion="deliver spreadsheets as xlsx",
            )
        ],
        meta_observation="the user prefers structured output",
    )


def llm_answering(response: PatternDiscoveryResponse) -> MagicMock:
    structured = AsyncMock()
    structured.ainvoke = AsyncMock(return_value=response)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {kind: count for kind, count in counts.items() if count}


async def discovered_after_seeding(manager: MemoryManager, extra: Sequence[AnyMemory] = ()) -> None:
    """Seed one memory per chat, the newest memory last, and run a discovery cycle over them."""
    await seed(manager, [semantic(f"note {i}", i, source_chat_id=chat(i)) for i in range(MEMORIES)])
    await seed(manager, extra)
    await write_bookkeeping(manager, _PROFILE_KEY_CONSOLIDATION_COUNT, "5")
    report = await run_pattern_discovery(manager, llm_answering(established_habit()))
    assert report.skipped is False


async def pattern_event(manager: MemoryManager) -> EpisodicMemory:
    [event] = [
        memory
        for memory in await manager.list_memories(MemoryType.EPISODIC, limit=10)
        if isinstance(memory, EpisodicMemory) and memory.event_type == "pattern_discovery"
    ]
    return event


async def test_the_event_and_the_promoted_rule_record_the_chats_of_the_memories_the_model_read(
    new_manager: NewManager,
) -> None:
    manager = new_manager(approval_required=True)

    await discovered_after_seeding(manager)

    read = [chat(i) for i in reversed(range(MEMORIES - MAX_PROMPT_MEMORIES, MEMORIES))]
    event = await pattern_event(manager)
    assert chat_links(event) == read
    [proposal] = await manager.list_pending()
    rule = ProceduralMemory.model_validate(proposal.memory_data)
    assert rule.source.value == "agent_self"
    assert chat_links(rule) == read


async def test_deleting_a_chat_the_model_read_removes_the_event_and_the_rule_proposal(
    new_manager: NewManager,
) -> None:
    manager = new_manager(approval_required=True)
    cascade = new_manager(all_scopes=True)
    await discovered_after_seeding(manager)

    preview = await cascade.count_by_source_chat_id(chat(MEMORIES - 1))
    purged = await cascade.purge_by_source_chat_id(chat(MEMORIES - 1))

    assert preview == {"semantic": 1, "episodic": 1, "pending": 1}
    assert nonzero(purged) == preview
    assert await manager.list_memories(MemoryType.EPISODIC, limit=10) == []
    assert await manager.list_pending() == []


async def test_deleting_a_chat_the_model_did_not_read_leaves_the_pattern(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    cascade = new_manager(all_scopes=True)
    await discovered_after_seeding(manager)

    purged = await cascade.purge_by_source_chat_id(chat(0))

    assert nonzero(purged) == {"semantic": 1}
    assert await pattern_event(manager) is not None
    assert len(await manager.list_pending()) == 1


async def test_the_rule_approved_from_a_pattern_goes_with_any_chat_the_model_read(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    cascade = new_manager(all_scopes=True)
    await discovered_after_seeding(manager)
    [proposal] = await manager.list_pending()
    rule = await manager.approve(proposal.id)

    purged = await cascade.purge_by_source_chat_id(chat(MEMORIES - MAX_PROMPT_MEMORIES))

    assert nonzero(purged) == {"semantic": 1, "episodic": 1, "procedural": 1, "pending": 1}
    assert await manager._rel().get_rule(rule.id) is None


async def test_an_insight_the_model_quotes_brings_its_chats_into_the_pattern(new_manager: NewManager) -> None:
    manager = new_manager()
    # Older than every listed memory, so the prompt does not list it: only the insight collection reaches it.
    insight = semantic(
        "consolidation insight pattern observation: the user keeps asking for spreadsheets",
        -10,
        tags=[CONSOLIDATION_INSIGHT_TAG],
        source_chat_id="chat-insight-b",
        source_chat_ids=["chat-insight-b", "chat-insight-a"],
    )

    await discovered_after_seeding(manager, [insight])

    assert {"chat-insight-a", "chat-insight-b"} <= set(chat_links(await pattern_event(manager)))
