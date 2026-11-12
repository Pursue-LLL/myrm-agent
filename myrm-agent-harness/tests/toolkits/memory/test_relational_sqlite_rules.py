"""SQLiteRelationalStore unit tests — procedural rules."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalNotFoundError
from myrm_agent_harness.toolkits.memory.types import (
    MemoryScope,
    ProceduralMemory,
)
from tests.support.relational_records import make_rule


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    s = SQLiteRelationalStore(str(tmp_path / "test_rel.db"))
    yield s
    await s.close()


# ── Procedural rules ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_rule(store: SQLiteRelationalStore) -> None:
    rule = make_rule()
    created = await store.create_rule(rule)
    assert created.id
    fetched = await store.get_rule(created.id)
    assert fetched is not None
    assert fetched.trigger == "user asks"


@pytest.mark.asyncio
async def test_get_rule_not_found(store: SQLiteRelationalStore) -> None:
    result = await store.get_rule("ghost")
    assert result is None


@pytest.mark.asyncio
async def test_search_rules(store: SQLiteRelationalStore) -> None:
    await store.create_rule(make_rule("file request", "use Excel"))
    await store.create_rule(make_rule("code review", "be strict"))
    results = await store.search_rules("file")
    assert len(results) == 1
    assert results[0].trigger == "file request"


@pytest.mark.asyncio
async def test_list_rules(store: SQLiteRelationalStore) -> None:
    await store.create_rule(make_rule("a", "1"))
    await store.create_rule(make_rule("b", "2"))
    rules = await store.list_rules()
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_count_rules(store: SQLiteRelationalStore) -> None:
    await store.create_rule(make_rule())
    assert await store.count_rules() == 1


@pytest.mark.asyncio
async def test_update_rule(store: SQLiteRelationalStore) -> None:
    created = await store.create_rule(make_rule("old", "old_action"))
    updated_rule = make_rule("new", "new_action")
    updated = await store.update_rule(created.id, updated_rule)
    assert updated.trigger == "new"
    fetched = await store.get_rule(created.id)
    assert fetched is not None
    assert fetched.action == "new_action"


@pytest.mark.asyncio
async def test_update_rule_not_found(store: SQLiteRelationalStore) -> None:
    with pytest.raises(RelationalNotFoundError):
        await store.update_rule("ghost", make_rule())


@pytest.mark.asyncio
async def test_delete_rule(store: SQLiteRelationalStore) -> None:
    created = await store.create_rule(make_rule())
    deleted = await store.delete_rule(created.id)
    assert deleted is True
    assert await store.get_rule(created.id) is None


@pytest.mark.asyncio
async def test_rules_are_filtered_by_namespace(store: SQLiteRelationalStore) -> None:
    telegram_rule = make_rule("telegram ask", "reply telegram")
    telegram_rule.scope = MemoryScope(
        primary_namespace="channel:telegram",
        namespaces=["global", "channel:telegram"],
        channel_id="telegram",
    )
    feishu_rule = make_rule("feishu ask", "reply feishu")
    feishu_rule.scope = MemoryScope(
        primary_namespace="channel:feishu",
        namespaces=["global", "channel:feishu"],
        channel_id="feishu",
    )

    await store.create_rule(telegram_rule)
    await store.create_rule(feishu_rule)

    telegram_results = await store.search_rules("ask", namespaces=["channel:telegram"])
    assert len(telegram_results) == 1
    assert telegram_results[0].scope.channel_id == "telegram"
    assert await store.count_rules(namespaces=["channel:feishu"]) == 1


# ── Tool-scoped rules ────────────────────────────────────────────────


def _make_tool_rule(
    tool_name: str, priority: str = "normal", trigger: str = "t", action: str = "a"
) -> ProceduralMemory:
    from myrm_agent_harness.toolkits.memory.types import ToolRulePriority

    return ProceduralMemory(
        content=f"When: {trigger} → Do: {action}",
        trigger=trigger,
        action=action,
        tool_name=tool_name,
        tool_rule_priority=ToolRulePriority(priority),
    )


@pytest.mark.asyncio
async def test_create_rule_with_tool_fields(store: SQLiteRelationalStore) -> None:
    """tool_name and tool_rule_priority are persisted and retrievable."""
    from myrm_agent_harness.toolkits.memory.types import ToolRulePriority

    rule = _make_tool_rule("bash_code_execute_tool", "critical", "using sudo", "reject")
    created = await store.create_rule(rule)
    fetched = await store.get_rule(created.id)
    assert fetched is not None
    assert fetched.tool_name == "bash_code_execute_tool"
    assert fetched.tool_rule_priority == ToolRulePriority.CRITICAL


@pytest.mark.asyncio
async def test_create_rule_persists_expected_valid_days(
    store: SQLiteRelationalStore,
) -> None:
    """expected_valid_days round-trips through create/get/update."""
    rule = _make_tool_rule(
        "web_fetch_tool",
        trigger="repeated timeout",
        action="retry with fallback",
    )
    rule.expected_valid_days = 1
    rule.metadata["origin"] = "tool_failure"
    created = await store.create_rule(rule)
    fetched = await store.get_rule(created.id)
    assert fetched is not None
    assert fetched.expected_valid_days == 1
    assert fetched.metadata.get("origin") == "tool_failure"

    fetched.expected_valid_days = 3
    updated = await store.update_rule(fetched.id, fetched)
    re_fetched = await store.get_rule(updated.id)
    assert re_fetched is not None
    assert re_fetched.expected_valid_days == 3

    listed = await store.list_rules(active_only=True)
    assert any(r.id == created.id and r.expected_valid_days == 3 for r in listed)


@pytest.mark.asyncio
async def test_update_rule_preserves_tool_fields(store: SQLiteRelationalStore) -> None:
    """update_rule correctly persists tool_name and tool_rule_priority."""
    from myrm_agent_harness.toolkits.memory.types import ToolRulePriority

    created = await store.create_rule(_make_tool_rule("web_fetch_tool", "normal"))
    updated_rule = _make_tool_rule("web_fetch_tool", "critical", "timeout retry", "use exponential backoff")
    updated = await store.update_rule(created.id, updated_rule)
    assert updated.tool_rule_priority == ToolRulePriority.CRITICAL

    fetched = await store.get_rule(created.id)
    assert fetched is not None
    assert fetched.tool_rule_priority == ToolRulePriority.CRITICAL
    assert fetched.tool_name == "web_fetch_tool"


@pytest.mark.asyncio
async def test_list_rules_active_only_false(store: SQLiteRelationalStore) -> None:
    rule = make_rule("trigger", "action")
    rule.is_active = False
    await store.create_rule(rule)
    await store.create_rule(make_rule("active trigger", "active action"))

    all_rules = await store.list_rules(active_only=False)
    assert len(all_rules) == 2

    active_rules = await store.list_rules(active_only=True)
    assert len(active_rules) == 1


# ── Rule order: newest first ─────────────────────────────────────────


def _rule_created_at(trigger: str, created_at: datetime) -> ProceduralMemory:
    rule = make_rule(trigger, "act")
    rule.created_at = created_at
    return rule


@pytest.mark.asyncio
async def test_rules_come_out_newest_first_whatever_order_they_were_stored_in(store: SQLiteRelationalStore) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for name, days in (("middle", 2), ("oldest", 1), ("newest", 3)):
        await store.create_rule(_rule_created_at(name, base + timedelta(days=days)))

    assert [rule.trigger for rule in await store.list_rules()] == ["newest", "middle", "oldest"]
    assert [rule.trigger for rule in await store.list_rules(active_only=False)] == ["newest", "middle", "oldest"]
    assert [rule.trigger for rule in await store.search_rules("act")] == ["newest", "middle", "oldest"]


@pytest.mark.asyncio
async def test_rules_created_in_the_same_instant_keep_a_stable_order(store: SQLiteRelationalStore) -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    for name in ("a", "b", "c"):
        await store.create_rule(_rule_created_at(name, instant))

    first = [rule.id for rule in await store.list_rules()]
    assert first == sorted(first, reverse=True)
    assert [rule.id for rule in await store.list_rules()] == first


@pytest.mark.asyncio
async def test_a_rule_keeps_the_creation_time_it_carries(store: SQLiteRelationalStore) -> None:
    proposed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    created = await store.create_rule(_rule_created_at("proposed", proposed_at))

    fetched = await store.get_rule(created.id)
    assert fetched is not None
    assert fetched.created_at == proposed_at
    assert fetched.updated_at > proposed_at


@pytest.mark.asyncio
async def test_creation_times_in_different_offsets_order_by_the_instant(store: SQLiteRelationalStore) -> None:
    """02:00Z written as 10:00+08:00 sorts after 03:00Z as text, but it is the earlier instant."""
    earlier = datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    later = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    await store.create_rule(_rule_created_at("earlier", earlier))
    await store.create_rule(_rule_created_at("later", later))

    assert [rule.trigger for rule in await store.list_rules()] == ["later", "earlier"]
