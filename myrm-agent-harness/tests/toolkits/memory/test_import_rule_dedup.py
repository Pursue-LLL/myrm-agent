"""``import_memories`` does not store a rule the manager already holds.

A rule has no natural key, so the writer never deduplicates one: importing the same file again stacked a second copy
of every rule on the first. The copy is the newer one, the prompt lists rules newest first and tells the model to follow
the earlier one when two conflict, so a stale rule's new copy outranked the preference the user had stated since.
Importing without ``skip_duplicates`` still writes every entry: a restore that replaces the store must land each one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory._manager.import_export.rule_dedup import rule_identity, without_known_rules
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, MemoryType, ProceduralMemory

_MIXIN = "myrm_agent_harness.toolkits.memory._manager.import_export.mixin"
_TRIGGER = "When replying to the user"
_ENGLISH = "Always reply to me in English"
_CHINESE = "Always reply to me in Chinese"


def _model(trigger: str, action: str, *, tool_name: str | None = None) -> ProceduralMemory:
    return ProceduralMemory(
        content=f"When: {trigger} → Do: {action}", trigger=trigger, action=action, tool_name=tool_name
    )


def _rule(trigger: str, action: str, *, tool_name: str | None = None) -> dict[str, object]:
    """One rule as an import carries it, stamped with the moment it was built."""
    return _model(trigger, action, tool_name=tool_name).model_dump(mode="json", exclude={"embedding"})


async def _stored(manager: MemoryManager) -> list[ProceduralMemory]:
    """Every stored rule, the disabled and archived ones included."""
    return list(await manager._rel().list_rules(active_only=False))


async def _prompt_rules(manager: MemoryManager) -> list[tuple[object, object]]:
    """(trigger, action) of the rules the prompt's rule block is built from, in the order it lists them."""
    rules = (await manager.get_context(include_profile=False))["rules"]
    assert isinstance(rules, list)
    return [(rule["trigger"], rule["action"]) for rule in rules if isinstance(rule, dict)]


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[MemoryManager]:
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.mark.slow
async def test_importing_the_same_rules_again_stores_each_once(manager: MemoryManager) -> None:
    rules = [_rule(_TRIGGER, _ENGLISH), _rule("When writing code", "Prefer small functions")]

    first = await manager.import_memories({"procedural": rules})
    second = await manager.import_memories({"procedural": rules})

    assert first == {"procedural": 2}
    assert second == {"procedural": 0}
    assert len(await _stored(manager)) == 2


@pytest.mark.slow
async def test_twin_rules_in_one_import_are_stored_once(manager: MemoryManager) -> None:
    counts = await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH), _rule(_TRIGGER, _ENGLISH)]})

    assert counts == {"procedural": 1}
    assert len(await _stored(manager)) == 1


@pytest.mark.slow
async def test_rules_that_differ_only_in_case_or_spacing_are_the_same_rule(manager: MemoryManager) -> None:
    await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    counts = await manager.import_memories(
        {"procedural": [_rule("  when   replying to the USER ", "always reply to  me in english")]}
    )

    assert counts == {"procedural": 0}
    assert len(await _stored(manager)) == 1


@pytest.mark.slow
async def test_a_rule_worded_differently_is_stored(manager: MemoryManager) -> None:
    await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    counts = await manager.import_memories(
        {"procedural": [_rule(_TRIGGER, _CHINESE), _rule("When reviewing a change", _ENGLISH)]}
    )

    assert counts == {"procedural": 2}
    assert len(await _stored(manager)) == 3


@pytest.mark.slow
async def test_a_rule_scoped_to_a_tool_is_not_the_global_rule_of_the_same_text(manager: MemoryManager) -> None:
    await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    counts = await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH, tool_name="bash")]})

    assert counts == {"procedural": 1}
    assert sorted(rule.tool_name or "" for rule in await _stored(manager)) == ["", "bash"]


@pytest.mark.slow
@pytest.mark.parametrize("status", [MemoryStatus.DISABLED, MemoryStatus.ARCHIVED])
async def test_a_rule_the_user_or_the_system_retired_is_not_brought_back_by_an_import(
    manager: MemoryManager, status: MemoryStatus
) -> None:
    retired = await manager.add_rule(_TRIGGER, _ENGLISH)
    await manager.update_memory(retired.id, status=status)

    counts = await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    assert counts == {"procedural": 0}
    (only,) = await _stored(manager)
    assert only.id == retired.id
    assert not only.is_active
    assert await manager.count_memories(MemoryType.PROCEDURAL) == 0


@pytest.mark.slow
async def test_importing_without_skipping_duplicates_writes_every_rule(manager: MemoryManager) -> None:
    await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    counts = await manager.import_memories(
        {"procedural": [_rule(_TRIGGER, _ENGLISH), _rule(_TRIGGER, _ENGLISH)]}, skip_duplicates=False
    )

    assert counts == {"procedural": 2}
    assert len(await _stored(manager)) == 3


@pytest.mark.slow
async def test_a_preference_stated_after_an_import_stays_ahead_of_the_same_import_made_again(
    manager: MemoryManager,
) -> None:
    await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})
    await manager.add_rule(_TRIGGER, _CHINESE)

    # An importer stamps what it builds with the moment it builds it, so the second file's copy is the newest rule.
    await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    assert await _prompt_rules(manager) == [(_TRIGGER, _CHINESE), (_TRIGGER, _ENGLISH)]


@pytest.mark.slow
async def test_a_rule_another_agent_holds_does_not_stop_the_import(tmp_path: Path) -> None:
    agent_a = await create_local_memory_manager(tmp_path / "mem", None, agent_id="agent-a")
    agent_b = await create_local_memory_manager(tmp_path / "mem", None, agent_id="agent-b")
    try:
        await agent_a.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

        counts = await agent_b.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

        assert counts == {"procedural": 1}
        assert len(await agent_b._rel().list_rules(active_only=False, namespaces=agent_b.namespaces)) == 1
    finally:
        await agent_b.close()
        await agent_a.close()


@pytest.mark.slow
async def test_a_stored_rule_beyond_the_first_page_is_still_recognized(
    manager: MemoryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(f"{_MIXIN}._RULE_PAGE_SIZE", 2)
    seeded = [_rule(_TRIGGER, f"Always reply in language {number}") for number in range(5)]
    await manager.import_memories({"procedural": seeded})

    counts = await manager.import_memories({"procedural": [*seeded, _rule(_TRIGGER, "Always reply in language 5")]})

    assert counts == {"procedural": 1}
    assert len(await _stored(manager)) == 6


@pytest.mark.slow
async def test_no_rule_is_imported_when_the_stored_rules_cannot_be_read(
    manager: MemoryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unreadable(**_kwargs: object) -> list[ProceduralMemory]:
        raise RuntimeError("store unavailable")

    with monkeypatch.context() as unreadable_store:
        unreadable_store.setattr(manager._rel(), "list_rules", unreadable)
        counts = await manager.import_memories({"procedural": [_rule(_TRIGGER, _ENGLISH)]})

    assert counts == {"procedural": 0}
    assert await _stored(manager) == []


def test_a_rules_identity_reads_spacing_and_letter_case_as_the_same() -> None:
    reworded = _model("  When  Replying\tto the USER ", "always reply to me  in english")

    assert rule_identity(reworded) == rule_identity(_model(_TRIGGER, _ENGLISH))


def test_a_rules_identity_tells_conditions_actions_and_tools_apart() -> None:
    base = rule_identity(_model(_TRIGGER, _ENGLISH))

    assert rule_identity(_model("When reviewing a change", _ENGLISH)) != base
    assert rule_identity(_model(_TRIGGER, _CHINESE)) != base
    assert rule_identity(_model(_TRIGGER, _ENGLISH, tool_name="bash")) != base


def test_without_known_rules_keeps_the_first_of_each_rule_in_order() -> None:
    first, other, repeat = _model(_TRIGGER, _ENGLISH), _model(_TRIGGER, _CHINESE), _model(_TRIGGER.lower(), _ENGLISH)

    assert without_known_rules([first, other, repeat], []) == [first, other]
    assert without_known_rules([first, other, repeat], [_model(_TRIGGER, _CHINESE)]) == [first]
