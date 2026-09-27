"""Pre-update snapshot orchestration for the Stack Update Panel.

[INPUT]
- myrm_agent_harness.observability.storage_governance::StateSnapshotManager (POS: SQLite hot-backup + manifest + restore/delete primitives)
- app.config.settings::get_settings (POS: state_dir resolution)

[OUTPUT]
- list_update_snapshots: newest-first snapshot inventory for the panel
- create_pre_update_snapshot: labeled snapshot + retention prune in one call
- prune_snapshots: keep-latest-N enforcement for pre-update labels

[POS]
Business-layer glue between the Stack Update Panel and the harness snapshot
primitives. Owns the `pre-update:{from}->{to}` label convention (update
manifest linkage), retention policy, and the honest Cloud unknown — the
harness manager itself stays generic and untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PRE_UPDATE_LABEL_PREFIX = "pre-update:"
DEFAULT_PRE_UPDATE_RETENTION = 5


@dataclass(slots=True)
class UpdateSnapshotItem:
    snapshot_id: str
    label: str
    size_bytes: int
    created_at: str
    from_version: str | None
    to_version: str | None


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
    prune_snapshots(data_dir, keep_latest=keep_latest)
    return UpdateSnapshotItem(
        snapshot_id=meta.snapshot_id,
        label=meta.label,
        size_bytes=meta.size_bytes,
        created_at=meta.created_at,
        from_version=from_version,
        to_version=to_version,
    )
