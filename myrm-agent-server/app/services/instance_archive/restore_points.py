"""Restore points: database snapshots taken before risky changes, restored at the next boot.

[INPUT]
- myrm_agent_harness.infra.state_archive (POS: consistent snapshots, free-space preflight)
- app.services.instance_archive.promotion_hook (POS: pre-boot swap queue)

[OUTPUT]
- RestorePoint: one stored snapshot (data.db + companion databases)
- list_restore_points / create_restore_point / delete_restore_point / prune_pre_update
- create_pre_update_point: labeled restore point + retention in one call
- stage_restore: verify a restore point and queue it for the next boot
- RestorePointError: stable machine-readable rejection

[POS]
Business-layer restore points (``{state_dir}/snapshots/<id>``). Creating one is a
page-consistent online copy; restoring never writes into the live database:
the copy is verified in staging and swapped in before any database opens, so a
running process can never overwrite or race the files it holds open.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.infra.state_archive import (
    InsufficientSpaceError,
    ensure_free_space,
    snapshot_sqlite,
)
from myrm_agent_harness.observability.storage_governance import StateSnapshotMetadata

from app.services.instance_archive.models import ArchivePaths, Operation, PendingPromotion, read_json, write_json_atomic
from app.services.instance_archive.policy import MAIN_DB_NAME
from app.services.instance_archive.promotion_hook import prepare_pending_for
from app.services.instance_archive.stage_db import StageRejected, verify_instance_db

logger = logging.getLogger(__name__)

PRE_UPDATE_LABEL_PREFIX = "pre-update:"
DEFAULT_PRE_UPDATE_RETENTION = 5
COMPANION_DBS = (
    "checkpoints.db",
)  # session-resume continuity; restore points rewind databases only, not the GB-scale vector store
_META_FILE = "meta.json"
_SIDECARS = ("-wal", "-shm", "-journal")


class RestorePointError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class RestorePoint:
    snapshot_id: str
    label: str
    size_bytes: int
    created_at: str
    from_version: str | None
    to_version: str | None
    files: list[str] = field(default_factory=list)

    def to_metadata(self) -> StateSnapshotMetadata:
        return StateSnapshotMetadata(
            snapshot_id=self.snapshot_id,
            label=self.label,
            size_bytes=self.size_bytes,
            created_at=self.created_at,
            file_count=len(self.files),
        )


def _root(state_dir: Path) -> Path:
    return state_dir / "snapshots"


def _point_dir(state_dir: Path, snapshot_id: str) -> Path:
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or snapshot_id in (".", ".."):
        raise RestorePointError("unknown_restore_point", "Unknown restore point")
    return _root(state_dir) / snapshot_id


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pre_update_label(label: str) -> tuple[str | None, str | None]:
    """Extract (from_version, to_version) from ``pre-update:{from}->{to}`` labels."""
    if not label.startswith(PRE_UPDATE_LABEL_PREFIX):
        return None, None
    from_version, _, to_version = label[len(PRE_UPDATE_LABEL_PREFIX) :].partition("->")
    return (from_version.strip() or None, to_version.strip() or None) if to_version.strip() else (None, None)


def _read_point(directory: Path) -> RestorePoint | None:
    raw = read_json(directory / _META_FILE)
    if raw is None:
        return None
    label = str(raw.get("label", "Restore point"))
    files = raw.get("files")
    if not isinstance(files, list):
        # Points whose metadata lists no files name their extra databases in a sidecar manifest.
        sidecar = read_json(directory / "extra_files.json")
        extra = sidecar.get("files") if sidecar else None
        files = [MAIN_DB_NAME, *(extra if isinstance(extra, list) else [])]
    from_version, to_version = parse_pre_update_label(label)
    size = raw.get("size_bytes")
    return RestorePoint(
        snapshot_id=str(raw.get("snapshot_id", directory.name)),
        label=label,
        size_bytes=size if isinstance(size, int) else 0,
        created_at=str(raw.get("created_at", "")),
        from_version=from_version,
        to_version=to_version,
        files=[str(name) for name in files],
    )


def list_restore_points(state_dir: Path) -> list[RestorePoint]:
    """Newest-first inventory."""
    root = _root(state_dir)
    if not root.is_dir():
        return []
    points = [p for child in root.iterdir() if child.is_dir() and (p := _read_point(child)) is not None]
    return sorted(points, key=lambda p: p.created_at, reverse=True)


def create_restore_point(state_dir: Path, label: str) -> RestorePoint:
    snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    directory = _point_dir(state_dir, snapshot_id)
    directory.mkdir(parents=True)
    try:
        sources = [name for name in (MAIN_DB_NAME, *COMPANION_DBS) if (state_dir / name).exists()]
        if MAIN_DB_NAME not in sources:
            raise RestorePointError("no_database", "There is no database to snapshot")
        ensure_free_space(_root(state_dir), sum((state_dir / n).stat().st_size for n in sources))
        checksums: dict[str, str] = {}
        for name in sources:
            snapshot_sqlite(state_dir / name, directory / name, compact=False)
            checksums[name] = _sha256(directory / name)
    except InsufficientSpaceError as exc:
        shutil.rmtree(directory, ignore_errors=True)
        raise RestorePointError("insufficient_space", "Not enough free disk space") from exc
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    point = RestorePoint(
        snapshot_id=snapshot_id,
        label=label or "Manual restore point",
        size_bytes=sum((directory / n).stat().st_size for n in sources),
        created_at=datetime.now(UTC).isoformat(),
        from_version=None,
        to_version=None,
        files=sources,
    )
    point.from_version, point.to_version = parse_pre_update_label(point.label)
    write_json_atomic(
        directory / _META_FILE,
        {
            "snapshot_id": point.snapshot_id,
            "label": point.label,
            "size_bytes": point.size_bytes,
            "created_at": point.created_at,
            "file_count": len(sources),
            "files": sources,
            "checksums": checksums,
        },
    )
    return point


def delete_restore_point(state_dir: Path, snapshot_id: str) -> bool:
    directory = _point_dir(state_dir, snapshot_id)
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True


def prune_pre_update(state_dir: Path, *, keep_latest: int = DEFAULT_PRE_UPDATE_RETENTION) -> int:
    """Delete the oldest ``pre-update:`` points beyond the retention window; manual points are kept."""
    pre_update = [p for p in list_restore_points(state_dir) if p.label.startswith(PRE_UPDATE_LABEL_PREFIX)]
    deleted = 0
    for point in pre_update[max(1, keep_latest) :]:
        try:
            deleted += int(delete_restore_point(state_dir, point.snapshot_id))
        except OSError as exc:
            logger.warning("Failed to prune restore point %s: %s", point.snapshot_id, exc)
    return deleted


def create_pre_update_point(
    state_dir: Path, *, from_version: str, to_version: str, keep_latest: int = DEFAULT_PRE_UPDATE_RETENTION
) -> RestorePoint:
    point = create_restore_point(state_dir, f"{PRE_UPDATE_LABEL_PREFIX}{from_version}->{to_version}")
    prune_pre_update(state_dir, keep_latest=keep_latest)
    return point


def stage_restore(state_dir: Path, snapshot_id: str, *, max_schema_version: int) -> PendingPromotion:
    """Verify the point's files in a private staging copy and queue the swap for the next boot."""
    paths = ArchivePaths(state_dir)
    if paths.pending.exists():
        raise RestorePointError("operation_pending", "Another restore is already waiting for a restart")
    source = _point_dir(state_dir, snapshot_id)
    point = _read_point(source) if source.is_dir() else None
    if point is None or MAIN_DB_NAME not in point.files:
        raise RestorePointError("unknown_restore_point", "Unknown restore point")
    meta = read_json(source / _META_FILE) or {}
    raw_checksums = meta.get("checksums")
    checksums = raw_checksums if isinstance(raw_checksums, dict) else {}

    staging = paths.staging / f"restore-{uuid.uuid4().hex[:12]}"
    try:
        ensure_free_space(paths.staging.parent, point.size_bytes)
        staging.mkdir(parents=True)
        for name in point.files:
            if "/" in name or not (source / name).is_file():
                raise RestorePointError("restore_point_incomplete", "The restore point is incomplete")
            shutil.copy2(source / name, staging / name)
            expected = checksums.get(name)
            if isinstance(expected, str) and expected and _sha256(staging / name) != expected:
                raise RestorePointError("restore_point_corrupt", "The restore point failed its integrity check")
        verify_instance_db(staging / MAIN_DB_NAME, max_schema_version)
    except InsufficientSpaceError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise RestorePointError("insufficient_space", "Not enough free disk space") from exc
    except StageRejected as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise RestorePointError(exc.code, str(exc)) from exc
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    entries = tuple(sorted({*point.files, *(f"{n}{s}" for n in point.files for s in _SIDECARS)}))
    return prepare_pending_for(
        paths,
        operation=Operation.RESTORE_POINT,
        staging=staging,
        aside=paths.aside / staging.name,
        entries=entries,
    )


__all__ = [
    "COMPANION_DBS",
    "DEFAULT_PRE_UPDATE_RETENTION",
    "PRE_UPDATE_LABEL_PREFIX",
    "RestorePoint",
    "RestorePointError",
    "create_pre_update_point",
    "create_restore_point",
    "delete_restore_point",
    "list_restore_points",
    "prune_pre_update",
    "stage_restore",
]
