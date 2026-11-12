"""The memory a merge creates carries on what its sources were: their scope, age, expiry, ids and chats.

A merge of year-old notes is a year-old note, not new knowledge: recall labels a memory's age by its stamps, the
forgetting and stale-review gates run on them, and the namespace it is written to decides who can read it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_SOURCE_KEY, MergeOp
from myrm_agent_harness.toolkits.memory.strategies.consolidation_product import build_merge_product
from myrm_agent_harness.toolkits.memory.types import MemoryScope, SemanticMemory
from tests.support.consolidation_cycles import merged_pair
from tests.support.consolidation_seeds import NewManager

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _source(
    created_days_ago: float,
    *,
    updated_days_ago: float | None = None,
    valid_days: int | None = None,
    **changes: object,
) -> SemanticMemory:
    source = SemanticMemory(
        content="a fact",
        created_at=NOW - created_days_ago * DAY,
        updated_at=NOW - (created_days_ago if updated_days_ago is None else updated_days_ago) * DAY,
        expected_valid_days=valid_days,
    )
    return source.model_copy(update=changes)


def _merge_of(*sources: SemanticMemory, importance: float = 0.7) -> MergeOp:
    return MergeOp(
        source_ids=[source.id for source in sources], merged_content="the merged fact", importance=importance
    )


def test_the_product_is_as_old_as_its_oldest_source_and_as_recently_updated_as_its_latest() -> None:
    old, recent = _source(200, updated_days_ago=150), _source(30, updated_days_ago=2)

    product = build_merge_product(_merge_of(recent, old), [recent, old])

    assert product.created_at == old.created_at
    assert product.updated_at == recent.updated_at


def test_the_product_expires_when_its_longest_lived_source_would_have() -> None:
    short, long = _source(40, valid_days=30), _source(10, valid_days=60)  # expire 10 days ago and 50 days ahead

    product = build_merge_product(_merge_of(short, long), [short, long])

    assert product.expected_valid_days == 90  # from the product's creation, 40 days ago, to the later expiry


def test_a_partial_day_of_validity_rounds_up() -> None:
    first, second = _source(10, valid_days=5), _source(4.5, valid_days=1)

    product = build_merge_product(_merge_of(first, second), [first, second])

    assert product.expected_valid_days == 7  # the later expiry is 6.5 days after the product's creation


def test_the_product_has_no_expiry_when_any_source_has_none() -> None:
    expiring, open_ended = _source(40, valid_days=30), _source(10)

    assert build_merge_product(_merge_of(expiring, open_ended), [expiring, open_ended]).expected_valid_days is None


def test_a_source_without_a_positive_window_leaves_the_product_open_ended() -> None:
    expiring, zero = _source(40, valid_days=30), _source(10, valid_days=0)

    assert build_merge_product(_merge_of(expiring, zero), [expiring, zero]).expected_valid_days is None


def test_the_product_stays_where_its_first_source_was_visible() -> None:
    scope = MemoryScope(primary_namespace="agent:x", namespaces=["agent:x", "global"], agent_id="x")
    first, second = (
        _source(5, scope=scope),
        _source(4, scope=MemoryScope(primary_namespace="global", namespaces=["global"])),
    )

    product = build_merge_product(_merge_of(first, second), [first, second])

    assert product.scope == scope and product.scope is not scope


def test_the_product_records_the_full_ids_of_its_sources_and_the_chats_of_all_of_them() -> None:
    older = _source(9, source_chat_ids=["chat-old"])
    newer = _source(3, source_chat_id="chat-new")

    product = build_merge_product(_merge_of(older, newer), [older, newer])

    assert product.metadata[CONSOLIDATION_SOURCE_KEY] == f"{older.id},{newer.id}"
    assert product.source_chat_ids == ["chat-new", "chat-old"]
    assert product.source_chat_id == "chat-new"


def test_how_a_memory_was_used_is_not_inherited() -> None:
    used = _source(9, importance=0.2, access_count=40, confidence=0.5)
    other = _source(8, importance=0.9, access_count=3)

    product = build_merge_product(_merge_of(used, other, importance=0.7), [used, other])

    assert (product.importance, product.confidence, product.access_count) == (0.7, 0.9, 0)


async def test_a_stored_product_keeps_the_age_of_its_sources(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second, merged_id = await merged_pair(manager)

    product = await manager.get_memory(merged_id)

    assert product is not None
    assert abs(product.created_at - first.created_at) < timedelta(seconds=1)
    assert product.created_at < datetime.now(UTC) - 29 * DAY  # seeded 30 days ago, so not "today"
    assert second.created_at > product.created_at
