"""Ledger status machine: identity, change detection, retry budget, dismissal and remote deletion."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.source_sync.ima.ledger import (
    MAX_ATTEMPTS,
    ImaLedger,
    InventoryItem,
    LedgerRow,
    LedgerStatus,
)

pytestmark = pytest.mark.usefixtures("ima_db")

SCOPE = "__default__"
CONTAINERS = ["kb1", "kb2", "other"]


def item(key: str, *, version: str = "v1", container: str = "kb1", title: str = "doc") -> InventoryItem:
    return InventoryItem(
        item_key=key,
        container_id=container,
        container_name="Lib",
        remote_id=f"remote-{key}",
        title=title,
        folder_path="",
        media_type=7,
        remote_version=version,
    )


async def _row(factory: async_sessionmaker[AsyncSession], key: str) -> LedgerRow:
    async with factory() as db:
        rows = await ImaLedger(SCOPE).list_rows(db, containers=CONTAINERS, limit=100)
    return next(row for row in rows if row.item_key == key)


async def _upsert(
    factory: async_sessionmaker[AsyncSession],
    items: list[InventoryItem],
    *,
    generation: int = 1,
    raw_exists: bool = True,
) -> int:
    async with factory() as db:
        added = await ImaLedger(SCOPE).upsert_inventory(db, items, generation=generation, raw_exists=lambda _path: raw_exists)
        await db.commit()
    return added


async def _sync(factory: async_sessionmaker[AsyncSession], key: str, *, path: str = "ima/Lib/doc-aaaa.md") -> None:
    row = await _row(factory, key)
    async with factory() as db:
        await ImaLedger(SCOPE).record_synced(db, row, raw_path=path, fidelity="full", notes=[], char_count=10)
        await db.commit()


async def test_new_items_start_pending_and_are_counted(ima_db: async_sessionmaker[AsyncSession]) -> None:
    assert await _upsert(ima_db, [item("a"), item("b")]) == 2
    assert await _upsert(ima_db, [item("a"), item("c")], generation=2) == 1
    assert (await _row(ima_db, "a")).status == LedgerStatus.PENDING


async def test_version_change_requeues_a_synced_item(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("a")])
    await _sync(ima_db, "a")

    await _upsert(ima_db, [item("a", version="v1")], generation=2)
    assert (await _row(ima_db, "a")).status == LedgerStatus.SYNCED

    await _upsert(ima_db, [item("a", version="v2")], generation=3)
    row = await _row(ima_db, "a")
    assert row.status == LedgerStatus.PENDING and row.remote_version == "v2" and row.synced_version == "v1"


async def test_missing_raw_file_means_the_user_dismissed_it_for_good(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("a")])
    await _sync(ima_db, "a")

    await _upsert(ima_db, [item("a")], generation=2, raw_exists=False)
    assert (await _row(ima_db, "a")).status == LedgerStatus.DISMISSED

    # Even a new remote version must not resurrect it.
    await _upsert(ima_db, [item("a", version="v9")], generation=3, raw_exists=True)
    assert (await _row(ima_db, "a")).status == LedgerStatus.DISMISSED


async def test_claim_orders_pending_before_failed_and_honours_the_retry_budget(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("p"), item("f1"), item("f2")])
    ledger = ImaLedger(SCOPE)
    first, second = await _row(ima_db, "f1"), await _row(ima_db, "f2")
    async with ima_db() as db:
        await ledger.record_failure(db, first, kind="transient")
        await ledger.record_failure(db, second, kind="permanent", final=True)
        await db.commit()

    async with ima_db() as db:
        claimed = await ledger.claim(db, limit=10, containers=["kb1"])
    assert [row.item_key for row in claimed] == ["p", "f1"]
    assert (await _row(ima_db, "f1")).attempts == 1
    assert (await _row(ima_db, "f2")).attempts == MAX_ATTEMPTS

    async with ima_db() as db:
        excluded = await ledger.claim(db, limit=10, containers=["kb1"], exclude=["p"])
        other_container = await ledger.claim(db, limit=10, containers=["other"])
    assert [row.item_key for row in excluded] == ["f1"]
    assert other_container == []


async def test_retry_failed_restores_the_budget(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("a")])
    ledger = ImaLedger(SCOPE)
    row = await _row(ima_db, "a")
    async with ima_db() as db:
        await ledger.record_failure(db, row, kind="permanent", final=True)
        await db.commit()
    async with ima_db() as db:
        assert await ledger.retry_failed(db, CONTAINERS) == 1
        await db.commit()
    row = await _row(ima_db, "a")
    assert row.status == LedgerStatus.PENDING and row.attempts == 0 and row.error_kind == ""


async def test_remote_deletion_only_touches_unseen_rows_in_clean_containers(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("seen"), item("gone"), item("dismissed"), item("elsewhere", container="kb2")])
    await _sync(ima_db, "dismissed")
    await _upsert(ima_db, [item("dismissed")], generation=2, raw_exists=False)
    await _upsert(ima_db, [item("seen")], generation=2)

    async with ima_db() as db:
        deleted = await ImaLedger(SCOPE).mark_remote_deleted(db, generation=2, container_ids=["kb1"])
        await db.commit()

    assert deleted == 1
    assert (await _row(ima_db, "gone")).status == LedgerStatus.REMOTE_DELETED
    assert (await _row(ima_db, "seen")).status == LedgerStatus.PENDING
    assert (await _row(ima_db, "dismissed")).status == LedgerStatus.DISMISSED
    assert (await _row(ima_db, "elsewhere")).status == LedgerStatus.PENDING


async def test_reappearing_item_returns_to_its_previous_state(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("a")])
    await _sync(ima_db, "a")
    async with ima_db() as db:
        await ImaLedger(SCOPE).mark_remote_deleted(db, generation=2, container_ids=["kb1"])
        await db.commit()
    assert (await _row(ima_db, "a")).status == LedgerStatus.REMOTE_DELETED

    await _upsert(ima_db, [item("a")], generation=3)
    assert (await _row(ima_db, "a")).status == LedgerStatus.SYNCED


async def test_counts_report_partial_fidelity_and_characters(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("a"), item("b"), item("c")])
    ledger = ImaLedger(SCOPE)
    row_a, row_b, row_c = await _row(ima_db, "a"), await _row(ima_db, "b"), await _row(ima_db, "c")
    async with ima_db() as db:
        await ledger.record_synced(db, row_a, raw_path="p/a.md", fidelity="full", notes=[], char_count=100)
        await ledger.record_synced(db, row_b, raw_path="p/b.md", fidelity="partial", notes=["layout_flattened"], char_count=50)
        await ledger.record_terminal(db, row_c, LedgerStatus.UNSUPPORTED, reason="unsupported_type")
        await db.commit()

    async with ima_db() as db:
        counts = await ledger.counts(db, CONTAINERS)
        lossy = await ledger.list_rows(db, containers=CONTAINERS, partial_only=True)
        paths = await ledger.synced_paths(db, CONTAINERS)
    assert counts.of(LedgerStatus.SYNCED) == 2 and counts.of(LedgerStatus.UNSUPPORTED) == 1
    assert counts.partial == 1 and counts.total_chars == 150 and counts.total == 3
    assert [row.fidelity_notes for row in lossy] == [("layout_flattened",)]
    assert sorted(paths) == ["p/a.md", "p/b.md"]


async def test_has_item_ignores_remote_deleted_but_not_dismissed(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("live"), item("deleted"), item("dismissed")])
    await _sync(ima_db, "dismissed")
    await _upsert(ima_db, [item("dismissed")], generation=2, raw_exists=False)
    ledger = ImaLedger(SCOPE)
    async with ima_db() as db:
        await ledger.mark_remote_deleted(db, generation=2, container_ids=["kb1"])
        await db.commit()
    async with ima_db() as db:
        assert await ledger.has_item(db, "live") is False  # seen_generation 1 < 2 → deleted
        assert await ledger.has_item(db, "dismissed") is True
        assert await ledger.has_item(db, "nope") is False


async def test_scopes_are_isolated(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("a")])
    async with ima_db() as db:
        assert (await ImaLedger("agent-x").counts(db, CONTAINERS)).total == 0


async def test_reads_and_retry_cover_only_the_selected_containers(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [item("keep", container="kb1"), item("drop", container="kb2")])
    ledger = ImaLedger(SCOPE)
    keep, drop = await _row(ima_db, "keep"), await _row(ima_db, "drop")
    async with ima_db() as db:
        await ledger.record_synced(db, keep, raw_path="p/keep.md", fidelity="full", notes=[], char_count=10)
        await ledger.record_synced(db, drop, raw_path="p/drop.md", fidelity="partial", notes=["layout_flattened"], char_count=90)
        await db.commit()

    async with ima_db() as db:
        counts = await ledger.counts(db, ["kb1"])
        listed = await ledger.list_rows(db, containers=["kb1"], statuses=[LedgerStatus.SYNCED])
        paths = await ledger.synced_paths(db, ["kb1"])
        nothing = await ledger.counts(db, [])
    assert (counts.total, counts.partial, counts.total_chars) == (1, 0, 10)
    assert [row.item_key for row in listed] == ["keep"] and paths == ["p/keep.md"]
    assert nothing.total == 0

    async with ima_db() as db:
        await ledger.record_failure(db, await _row(ima_db, "keep"), kind="permanent", final=True)
        await ledger.record_failure(db, await _row(ima_db, "drop"), kind="permanent", final=True)
        await db.commit()
    async with ima_db() as db:
        assert await ledger.retry_failed(db, ["kb1"]) == 1
        await db.commit()
    assert (await _row(ima_db, "keep")).status == LedgerStatus.PENDING
    assert (await _row(ima_db, "drop")).status == LedgerStatus.FAILED


def sibling(media_id: str, *, base: str = "base", title: str = "Home", version: str | None = None) -> InventoryItem:
    """An item whose (kb, folder, title) key is ``base``; ``media_id`` distinguishes it from same-titled siblings."""
    return InventoryItem(
        item_key=base,
        fallback_key=f"{base}:{media_id}",
        container_id="kb1",
        container_name="Lib",
        remote_id=media_id,
        title=title,
        folder_path="",
        media_type=7,
        remote_version=version or media_id,
    )


async def _keys(factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with factory() as db:
        rows = await ImaLedger(SCOPE).list_rows(db, containers=CONTAINERS, limit=100)
    return {row.item_key: row.remote_id for row in rows}


async def test_same_title_siblings_in_one_batch_each_get_a_row(ima_db: async_sessionmaker[AsyncSession]) -> None:
    added = await _upsert(ima_db, [sibling("m1"), sibling("m2"), sibling("m3")])

    assert added == 3
    assert await _keys(ima_db) == {"base": "m1", "base:m2": "m2", "base:m3": "m3"}


async def test_same_title_siblings_split_across_pages_keep_their_keys(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [sibling("m1")])
    assert await _upsert(ima_db, [sibling("m2")]) == 1
    # A page fetched again after a restart resolves to the very same rows.
    assert await _upsert(ima_db, [sibling("m1"), sibling("m2")]) == 0

    assert await _keys(ima_db) == {"base": "m1", "base:m2": "m2"}


async def test_siblings_keep_their_keys_in_the_next_pass_and_unseen_ones_are_marked_gone(
    ima_db: async_sessionmaker[AsyncSession],
) -> None:
    await _upsert(ima_db, [sibling("m1"), sibling("m2")])
    assert await _upsert(ima_db, [sibling("m1"), sibling("m2")], generation=2) == 0

    assert await _upsert(ima_db, [sibling("m1")], generation=3) == 0
    async with ima_db() as db:
        assert await ImaLedger(SCOPE).mark_remote_deleted(db, generation=3, container_ids=["kb1"]) == 1
        await db.commit()
    assert (await _row(ima_db, "base:m2")).status == LedgerStatus.REMOTE_DELETED
    assert (await _row(ima_db, "base")).status == LedgerStatus.PENDING


async def test_a_replaced_file_updates_its_row_instead_of_becoming_a_sibling(ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _upsert(ima_db, [sibling("m1")])
    await _sync(ima_db, "base")

    # Same title, new media id, in a later pass: ima replaced the file in place.
    assert await _upsert(ima_db, [sibling("m9")], generation=2) == 0

    row = await _row(ima_db, "base")
    assert row.remote_id == "m9" and row.status == LedgerStatus.PENDING and row.synced_version == "m1"
    assert list(await _keys(ima_db)) == ["base"]


async def test_the_same_remote_item_listed_twice_in_one_batch_is_one_row(ima_db: async_sessionmaker[AsyncSession]) -> None:
    assert await _upsert(ima_db, [sibling("m1"), sibling("m1")]) == 1
    assert await _keys(ima_db) == {"base": "m1"}
