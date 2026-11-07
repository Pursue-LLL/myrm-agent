"""Pattern discovery reads the newest memories and the newest pattern events, not an arbitrary few.

An unordered scroll returns whichever documents the store lists first. Once a store holds more than a scroll
asks for, that is an arbitrary sample: the discovery prompt that claims to list the most recent memories lists
old ones, the memory-set hash cannot see a memory that arrived outside the sample, and the heartbeat is shown a
stale pattern in place of the latest. Each case drives a real manager over SQLite and an embedded Qdrant.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    get_recent_patterns,
    increment_consolidation_count,
    run_pattern_discovery,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_models import PatternDiscoveryResponse
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory

_FIRST = datetime(2026, 1, 1, tzinfo=UTC)
# More memories than the 200 a discovery run samples per type.
_STORE_SIZE = 450
_SAMPLE = 200
_LISTED_IN_PROMPT = 100
# The greatest id a random uuid4 can take: a store pages through its points by id, so the arrival that holds
# it is the last one an unordered sample of the store would reach.
_LAST_ID = "ffffffff-ffff-4fff-bfff-ffffffffffff"


def _fact(index: int, **fields: str) -> SemanticMemory:
    return SemanticMemory(content=f"fact {index:03d}", created_at=_FIRST + timedelta(hours=index), **fields)


def _pattern_event(day: int, content: str | None = None, *, event_type: str = "pattern_discovery") -> EpisodicMemory:
    return EpisodicMemory(
        content=content or f"pattern {day:02d}", event_type=event_type, created_at=_FIRST + timedelta(days=day)
    )


def _llm_recording_prompts() -> tuple[MagicMock, AsyncMock]:
    structured = AsyncMock()
    structured.ainvoke = AsyncMock(return_value=PatternDiscoveryResponse())
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm, structured.ainvoke


def _listed_facts(ainvoke: AsyncMock, call: int) -> list[int]:
    """The facts the ``call``-th discovery prompt lists, in the order it lists them."""
    prompt = ainvoke.await_args_list[call].args[0][1].content
    return [int(number) for number in re.findall(r"fact (\d{3})", prompt)]


async def _seed_mature_store(manager: MemoryManager) -> None:
    order = list(range(_STORE_SIZE))
    random.Random(11).shuffle(order)
    await manager.store_batch([_fact(index) for index in order], _bypass_approval=True, _skip_dedup=True)
    for _ in range(3):
        await increment_consolidation_count(manager)


async def test_the_prompt_lists_the_newest_memories_of_a_larger_store(
    new_manager: Callable[..., MemoryManager],
) -> None:
    manager = new_manager()
    await _seed_mature_store(manager)
    llm, ainvoke = _llm_recording_prompts()

    report = await run_pattern_discovery(manager, llm)

    assert not report.skipped, report.skip_reason
    assert report.memory_count == _SAMPLE
    newest_first = list(range(_STORE_SIZE - 1, _STORE_SIZE - 1 - _LISTED_IN_PROMPT, -1))
    assert _listed_facts(ainvoke, 0) == newest_first


async def test_a_memory_that_arrives_in_a_larger_store_changes_the_set_discovery_sees(
    new_manager: Callable[..., MemoryManager],
) -> None:
    manager = new_manager()
    await _seed_mature_store(manager)
    llm, ainvoke = _llm_recording_prompts()
    first = await run_pattern_discovery(manager, llm)
    unchanged = await run_pattern_discovery(manager, llm)

    await manager.store(_fact(_STORE_SIZE, id=_LAST_ID), _bypass_approval=True)
    after_arrival = await run_pattern_discovery(manager, llm)

    assert not first.skipped
    assert unchanged.skipped
    assert "unchanged" in unchanged.skip_reason
    assert not after_arrival.skipped, after_arrival.skip_reason
    assert ainvoke.await_count == 2
    assert _listed_facts(ainvoke, 1)[0] == _STORE_SIZE


async def test_the_heartbeat_gets_the_newest_pattern_events_of_its_owner(
    new_manager: Callable[..., MemoryManager],
) -> None:
    manager = new_manager()
    days = list(range(30))
    random.Random(11).shuffle(days)
    for day in days:
        await manager.store(_pattern_event(day), _bypass_approval=True)
    # Newer events of another owner and of another kind never stand in for the owner's own patterns.
    await new_manager(namespaces=["other"]).store(_pattern_event(99, "pattern of another owner"), _bypass_approval=True)
    await manager.store(_pattern_event(98, "a chat turn", event_type="conversation"), _bypass_approval=True)

    assert await get_recent_patterns(manager, limit=3) == ["pattern 29", "pattern 28", "pattern 27"]
