"""Memory snapshot capture/apply on real stores.

[INPUT]
app.services.memory.backup.snapshot::capture_snapshot/apply_snapshot/encode_snapshot/decode_snapshot

[OUTPUT]
Round-trip, fail-loud capture, replace/merge restore and decode-rejection tests.

[POS]
Real MemoryManager on real embedded Qdrant + SQLite (only embeddings are offline), so the
tests prove what a backup keeps and what a restore reproduces, not what a mock returns.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.services.memory.backup.snapshot import (
    MemorySnapshot,
    SnapshotError,
    apply_snapshot,
    capture_snapshot,
    decode_snapshot,
    encode_snapshot,
)
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration

_SEEDED_COUNTS = {"profile": 1, "procedural": 1, "semantic": 2, "episodic": 1}


async def _seed(manager: MemoryManager) -> None:
    pinned = await manager.add_knowledge("User prefers dark mode in every editor.", importance=0.9, tags=["ui"])
    await manager.pin_memory(pinned.id)
    await manager.add_knowledge("The release checklist lives in docs/release.md.")
    await manager.add_event("Deployed v2 on Friday and rolled back.", event_type="task_digest")
    await manager.add_rule("deploying", "run smoke tests first")
    await manager.set_profile_attribute("name", "Alice")


async def _content(manager: MemoryManager) -> dict[str, list[tuple[object, ...]]]:
    """What a user can observe per type, independent of generated ids and timestamps."""
    semantic = await manager.list_memories(MemoryType.SEMANTIC, limit=100)
    episodic = await manager.list_memories(MemoryType.EPISODIC, limit=100)
    rules = await manager.list_memories(MemoryType.PROCEDURAL, limit=100)
    profile = await manager.list_memories(MemoryType.PROFILE, limit=100)
    return {
        "semantic": sorted((m.content, m.importance, m.pinned, tuple(m.tags)) for m in semantic),
        "episodic": sorted((m.content, m.event_type) for m in episodic),
        "procedural": sorted((m.trigger, m.action) for m in rules),
        "profile": sorted((m.metadata["key"], m.metadata["value"]) for m in profile),
    }


async def test_replace_restore_reproduces_every_snapshot_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with (
        offline_memory_manager(tmp_path / "source", monkeypatch) as source,
        offline_memory_manager(tmp_path / "target", monkeypatch) as target,
    ):
        await _seed(source)

        snapshot = await capture_snapshot(source)
        assert {name: len(items) for name, items in snapshot.memories.items()} == _SEEDED_COUNTS

        counts = await apply_snapshot(target, snapshot, replace=True)

        assert counts == _SEEDED_COUNTS
        assert await _content(target) == await _content(source)
        # Digests live in the episodic collection, so they come back with it.
        assert await target.count_memories(MemoryType.TASK_DIGEST) == 1


async def test_replace_restore_removes_memories_that_are_not_in_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with (
        offline_memory_manager(tmp_path / "source", monkeypatch) as source,
        offline_memory_manager(tmp_path / "target", monkeypatch) as target,
    ):
        await _seed(source)
        await target.add_knowledge("Only the target knows this fact.")
        await target.add_rule("greeting", "say hello")
        await target.set_profile_attribute("city", "Berlin")
        snapshot = await capture_snapshot(source)

        await apply_snapshot(target, snapshot, replace=True)
        await apply_snapshot(target, snapshot, replace=True)

        assert await _content(target) == await _content(source)


async def test_merge_restore_keeps_existing_memories_and_never_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with (
        offline_memory_manager(tmp_path / "source", monkeypatch) as source,
        offline_memory_manager(tmp_path / "target", monkeypatch) as target,
    ):
        await _seed(source)
        await target.add_knowledge("Only the target knows this fact.")
        await target.add_rule("greeting", "say hello")
        snapshot = await capture_snapshot(source)

        await apply_snapshot(target, snapshot, replace=False)
        after_first_merge = await _content(target)
        await apply_snapshot(target, snapshot, replace=False)

        assert await _content(target) == after_first_merge
        assert ("Only the target knows this fact.", 0.5, False, ()) in after_first_merge["semantic"]
        assert ("greeting", "say hello") in after_first_merge["procedural"]
        assert ("deploying", "run smoke tests first") in after_first_merge["procedural"]
        assert len(after_first_merge["semantic"]) == 3
        assert len(after_first_merge["procedural"]) == 2
        assert len(after_first_merge["episodic"]) == 1


async def test_capture_fails_instead_of_returning_an_incomplete_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        await _seed(manager)
        real_export = manager.export_all

        async def export_without_semantic() -> dict[str, list[dict[str, object]]]:
            exported = await real_export()
            exported.pop("semantic")
            return exported

        monkeypatch.setattr(manager, "export_all", export_without_semantic)

        with pytest.raises(SnapshotError, match=r"semantic \(0 of 2\)"):
            await capture_snapshot(manager)


async def test_capture_of_an_empty_store_is_a_valid_empty_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        snapshot = await capture_snapshot(manager)

    assert snapshot.memories == {}
    assert snapshot.memory_count == 0


async def test_apply_refuses_a_manager_that_routes_writes_to_the_approval_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with (
        offline_memory_manager(tmp_path / "source", monkeypatch) as source,
        offline_memory_manager(tmp_path / "target", monkeypatch, approval_required=True) as target,
    ):
        await _seed(source)
        snapshot = await capture_snapshot(source)

        with pytest.raises(SnapshotError, match="approval queue"):
            await apply_snapshot(target, snapshot, replace=False)

        assert await target.count_memories(MemoryType.SEMANTIC) == 0


async def test_replace_restore_reports_entries_that_did_not_land(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with (
        offline_memory_manager(tmp_path / "source", monkeypatch) as source,
        offline_memory_manager(tmp_path / "target", monkeypatch) as target,
    ):
        await _seed(source)
        snapshot = await capture_snapshot(source)
        snapshot.memories["semantic"].append({"content": "", "memory_type": "not-a-memory-type"})

        with pytest.raises(SnapshotError, match=r"Restore incomplete: semantic \(2 of 3\)"):
            await apply_snapshot(target, snapshot, replace=True)


def test_encode_decode_round_trips_the_snapshot() -> None:
    snapshot = MemorySnapshot(
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
        memories={"semantic": [{"content": "mémoire 记忆", "importance": 0.5}]},
    )

    assert decode_snapshot(encode_snapshot(snapshot)) == snapshot


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not gzip at all", "corrupt"),
        (gzip.compress(b"{truncated"), "corrupt"),
        (gzip.compress(b"[1, 2, 3]"), "Unsupported backup format version: None"),
        (gzip.compress(json.dumps({"version": 2, "collections": {}}).encode()), "Unsupported backup format version: 2"),
        (gzip.compress(json.dumps({"version": 3, "memories": {}}).encode()), "invalid structure"),
        (
            gzip.compress(json.dumps({"version": 3, "created_at": "2026-10-13T00:00:00Z", "memories": {"claim": []}}).encode()),
            "invalid structure",
        ),
    ],
)
def test_decode_rejects_files_that_are_not_a_current_memory_backup(payload: bytes, message: str) -> None:
    with pytest.raises(SnapshotError, match=message):
        decode_snapshot(payload)
