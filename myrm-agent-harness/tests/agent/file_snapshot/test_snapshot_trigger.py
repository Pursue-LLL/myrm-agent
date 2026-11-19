"""A stored snapshot is read with a trigger this version may not know: it is listed and cleaned up, never hidden."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.file_snapshot.local_store import LocalFileSnapshotStore
from myrm_agent_harness.agent.file_snapshot.types import SnapshotTrigger


@pytest.fixture
def store(tmp_path: Path) -> LocalFileSnapshotStore:
    return LocalFileSnapshotStore(storage_path=tmp_path / "local_snapshots")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("print('main')\n")
    return ws


def _rewrite_manifest(store: LocalFileSnapshotStore, snapshot_id: str, **fields: object) -> None:
    """Rewrite fields of a stored manifest, as another version or an earlier moment would have written them."""
    snap_dir = store._find_snapshot_dir(snapshot_id)
    assert snap_dir is not None
    manifest_path = snap_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(fields)
    manifest_path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("trigger", list(SnapshotTrigger))
def test_from_stored_reads_every_trigger_this_version_reports(trigger: SnapshotTrigger) -> None:
    assert SnapshotTrigger.from_stored(trigger.value) is trigger


@pytest.mark.parametrize("stored", ["patch_file", "turn_completed", "a_trigger_from_a_newer_version", ""])
def test_from_stored_reads_an_unknown_trigger_as_manual(stored: str) -> None:
    assert SnapshotTrigger.from_stored(stored) is SnapshotTrigger.MANUAL


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", ["patch_file", "a_trigger_from_a_newer_version"])
async def test_a_snapshot_naming_an_unknown_trigger_is_still_listed(
    store: LocalFileSnapshotStore, workspace: Path, stored: str
) -> None:
    snapshot_id = await store.take_snapshot(str(workspace), SnapshotTrigger.WRITE_FILE, "written by another version")
    _rewrite_manifest(store, snapshot_id, trigger=stored)

    snapshots = await store.list_snapshots(str(workspace))

    assert [(s.snapshot_id, s.trigger) for s in snapshots] == [(snapshot_id, SnapshotTrigger.MANUAL)]


@pytest.mark.asyncio
async def test_cleanup_reaches_a_snapshot_naming_an_unknown_trigger(
    store: LocalFileSnapshotStore, workspace: Path
) -> None:
    """A snapshot the listing hides is one cleanup never sees, so it would stay on disk for good."""
    oldest = await store.take_snapshot(str(workspace), SnapshotTrigger.MANUAL, "oldest")
    middle = await store.take_snapshot(str(workspace), SnapshotTrigger.MANUAL, "middle")
    newest = await store.take_snapshot(str(workspace), SnapshotTrigger.MANUAL, "newest")
    _rewrite_manifest(store, oldest, trigger="a_trigger_from_a_newer_version", created_at=1.0)
    _rewrite_manifest(store, middle, created_at=2.0)
    _rewrite_manifest(store, newest, created_at=3.0)

    deleted = await store.cleanup(str(workspace), max_snapshots=1)

    assert deleted == 2
    assert [s.snapshot_id for s in await store.list_snapshots(str(workspace))] == [newest]
    assert store._find_snapshot_dir(oldest) is None
