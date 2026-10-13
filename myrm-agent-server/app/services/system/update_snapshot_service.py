"""Pre-update snapshot orchestration for the Stack Update Panel.

[INPUT]
- myrm_agent_harness.observability.storage_governance::StateSnapshotManager (POS: SQLite hot-backup + manifest + restore/delete primitives for data.db)
- app.config.settings::get_settings (POS: state_dir resolution)

[OUTPUT]
- list_update_snapshots: newest-first snapshot inventory for the panel
- create_pre_update_snapshot: labeled snapshot + retention prune in one call
- restore_update_snapshot: data.db via manager + extra DBs from sidecar manifest
- prune_snapshots: keep-latest-N enforcement for pre-update labels

[POS]
Business-layer glue between the Stack Update Panel and the harness snapshot
primitives. Owns the `pre-update:{from}->{to}` label convention (update
manifest linkage), the checkpoints.db sidecar (session-resume continuity),
retention policy, and the honest Cloud unknown — the harness manager itself
stays generic and untouched.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

PRE_UPDATE_LABEL_PREFIX = "pre-update:"
DEFAULT_PRE_UPDATE_RETENTION = 5
EXTRA_FILES_MANIFEST = "extra_files.json"
# Companion databases snapshotted alongside data.db (same hot-backup pattern).
# Qdrant is deliberately excluded: rebuildable vector index, GB-scale.
EXTRA_SNAPSHOT_DBS = ("checkpoints.db",)


@dataclass(slots=True)
class UpdateSnapshotItem:
    snapshot_id: str
    label: str
    size_bytes: int
    created_at: str
    from_version: str | None
    to_version: str | None
    extra_files: list[str] = field(default_factory=list)


def _manager(data_dir: Path | str):  # type: ignore[no-untyped-def]
    from myrm_agent_harness.observability.storage_governance import StateSnapshotManager

    return StateSnapshotManager(data_dir)


def _parse_manifest_label(label: str) -> tuple[str | None, str | None]:
    """Extract (from_version, to_version) from `pre-update:{from}->{to}` labels."""
    if not label.startswith(PRE_UPDATE_LABEL_PREFIX):
        return None, None
    remainder = label[len(PRE_UPDATE_LABEL_PREFIX):]
    if "->" not in remainder:
        return None, None
    from_version, _, to_version = remainder.partition("->")
    from_version = from_version.strip() or None
    to_version = to_version.strip() or None
    if not from_version or not to_version:
        return None, None
    return from_version, to_version


def list_update_snapshots(data_dir: Path | str) -> list[UpdateSnapshotItem]:
    """Newest-first inventory of all snapshots with manifest linkage parsed."""
    manager = _manager(data_dir)
    items: list[UpdateSnapshotItem] = []
    for meta in manager.list_snapshots():
        from_version, to_version = _parse_manifest_label(meta.label)
        items.append(
            UpdateSnapshotItem(
                snapshot_id=meta.snapshot_id,
                label=meta.label,
                size_bytes=meta.size_bytes,
                created_at=meta.created_at,
                from_version=from_version,
                to_version=to_version,
                extra_files=_read_extra_files(data_dir, meta.snapshot_id),
            )
        )
    return items


def prune_snapshots(data_dir: Path | str, *, keep_latest: int = DEFAULT_PRE_UPDATE_RETENTION) -> int:
    """Delete oldest pre-update snapshots beyond the retention window.

    Only touches `pre-update:` labeled snapshots; manual snapshots are never
    pruned automatically. Returns the number of deleted snapshots.
    """
    manager = _manager(data_dir)
    pre_update = [
        meta
        for meta in manager.list_snapshots()
        if meta.label.startswith(PRE_UPDATE_LABEL_PREFIX)
    ]
    if len(pre_update) <= max(1, keep_latest):
        return 0
    # list_snapshots returns newest-first; prune from the tail.
    victims = pre_update[max(1, keep_latest):]
    deleted = 0
    for meta in victims:
        try:
            if manager.delete_snapshot(meta.snapshot_id):
                deleted += 1
        except Exception as exc:
            logger.warning("Failed to prune snapshot %s: %s", meta.snapshot_id, exc)
    return deleted


def _hot_backup_file(src: Path, dest: Path) -> bool:
    """Online SQLite backup for companion DBs; False when absent or failed."""
    if not src.exists():
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        src_conn = sqlite3.connect(str(src), timeout=5.0)
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            src_conn.close()
        return True
    except Exception as exc:
        logger.warning("Companion DB backup failed for %s: %s", src, exc)
        return False


def _snapshot_dir(data_dir: Path | str, snapshot_id: str) -> Path:
    return Path(data_dir) / "snapshots" / snapshot_id


def _read_extra_files(data_dir: Path | str, snapshot_id: str) -> list[str]:
    sidecar = _snapshot_dir(data_dir, snapshot_id) / EXTRA_FILES_MANIFEST
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return []
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        return []
    return [name for name in files if isinstance(name, str)]


def create_pre_update_snapshot(
    data_dir: Path | str,
    *,
    from_version: str,
    to_version: str,
    keep_latest: int = DEFAULT_PRE_UPDATE_RETENTION,
) -> UpdateSnapshotItem:
    """Snapshot before an update install, then enforce retention."""
    manager = _manager(data_dir)
    label = f"{PRE_UPDATE_LABEL_PREFIX}{from_version}->{to_version}"
    meta = manager.create_snapshot(label=label)
    extra_files: list[str] = []
    total_size = meta.size_bytes
    for filename in EXTRA_SNAPSHOT_DBS:
        dest = _snapshot_dir(data_dir, meta.snapshot_id) / filename
        if _hot_backup_file(Path(data_dir) / filename, dest):
            extra_files.append(filename)
            try:
                total_size += dest.stat().st_size
            except OSError:
                pass
    if extra_files:
        sidecar = _snapshot_dir(data_dir, meta.snapshot_id) / EXTRA_FILES_MANIFEST
        try:
            sidecar.write_text(json.dumps({"files": extra_files}), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to write snapshot sidecar: %s", exc)
    prune_snapshots(data_dir, keep_latest=keep_latest)
    return UpdateSnapshotItem(
        snapshot_id=meta.snapshot_id,
        label=meta.label,
        size_bytes=total_size,
        created_at=meta.created_at,
        from_version=from_version,
        to_version=to_version,
        extra_files=extra_files,
    )


def restore_update_snapshot(data_dir: Path | str, snapshot_id: str) -> bool:
    """Restore data.db via the manager plus snapshotted companion DBs.

    Returns False when the snapshot is missing or integrity fails. Callers
    must restart the backend afterwards: in-memory caches go stale.
    """
    data_path = Path(data_dir)
    manager = _manager(data_path)
    if not manager.restore_snapshot(snapshot_id):
        return False
    for filename in _read_extra_files(data_path, snapshot_id):
        live = data_path / filename
        backup = _snapshot_dir(data_path, snapshot_id) / filename
        try:
            src_conn = sqlite3.connect(str(backup))
            dest_conn = sqlite3.connect(str(live))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
                src_conn.close()
        except Exception as exc:
            logger.error("Failed to restore companion DB %s: %s", filename, exc)
            return False
    return True
