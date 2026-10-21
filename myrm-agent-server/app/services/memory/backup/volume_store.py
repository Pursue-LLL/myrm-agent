"""Persistent-volume storage of memory snapshots.

[INPUT]
app.services.memory.backup.snapshot::MemorySnapshot/encode_snapshot/decode_snapshot (POS: 备份快照契约)
myrm_agent_harness.toolkits.memory.backup::BackupMetadata (POS: 框架备份元数据值对象)

[OUTPUT]
BackupNotFoundError / VolumeBackupStore

[POS]
把 MemorySnapshot 以 ``~/.myrm/backups/{backup_id}/`` 目录形式存放在沙箱持久卷上。备份 id 只接受本模块生成的格式，
因此 id 永远无法越出备份根目录；``metadata.json`` 最后写入，目录里没有它就不是一份完整备份。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from myrm_agent_harness.toolkits.memory.backup import BackupMetadata

from app.services.memory.backup.snapshot import MemorySnapshot, decode_snapshot, encode_snapshot

logger = logging.getLogger(__name__)

_SNAPSHOT_FILE: Final = "snapshot.json.gz"
_METADATA_FILE: Final = "metadata.json"
_BACKUP_ID_PATTERN: Final = re.compile(r"^memory_\d{8}_\d{6}_[0-9a-f]{8}$")


class BackupNotFoundError(Exception):
    """No complete backup exists under the requested id."""


class VolumeBackupStore:
    """Saves, lists, loads and deletes snapshots under one backup root (default ``~/.myrm/backups``)."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path.home() / ".myrm" / "backups"

    def save(self, snapshot: MemorySnapshot, description: str | None = None) -> BackupMetadata:
        created_at = datetime.now(UTC)
        backup_id = f"memory_{created_at:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        payload = encode_snapshot(snapshot)
        metadata = BackupMetadata(
            backup_id=backup_id,
            created_at=created_at,
            memory_count=snapshot.memory_count,
            size_bytes=len(payload),
            collections=sorted(snapshot.memories),
            description=description,
        )

        directory = self._root / backup_id
        directory.mkdir(parents=True)
        try:
            _write_atomically(directory / _SNAPSHOT_FILE, payload)
            _write_atomically(directory / _METADATA_FILE, _encode_metadata(metadata))
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return metadata

    def list_backups(self) -> list[BackupMetadata]:
        """Complete backups, newest first. Unreadable entries are logged and skipped."""
        if not self._root.is_dir():
            return []
        backups: list[BackupMetadata] = []
        for directory in self._root.iterdir():
            if not _BACKUP_ID_PATTERN.match(directory.name) or not (directory / _METADATA_FILE).is_file():
                continue
            try:
                backups.append(_decode_metadata((directory / _METADATA_FILE).read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning("Skipping unreadable memory backup %s: %s", directory.name, exc)
        return sorted(backups, key=lambda backup: backup.created_at, reverse=True)

    def load(self, backup_id: str) -> MemorySnapshot:
        return decode_snapshot((self._existing_directory(backup_id) / _SNAPSHOT_FILE).read_bytes())

    def delete(self, backup_id: str) -> bool:
        try:
            directory = self._existing_directory(backup_id)
        except BackupNotFoundError:
            return False
        shutil.rmtree(directory)
        return True

    def _existing_directory(self, backup_id: str) -> Path:
        directory = self._root / backup_id
        if not _BACKUP_ID_PATTERN.match(backup_id) or not (directory / _METADATA_FILE).is_file():
            raise BackupNotFoundError(f"Backup not found: {backup_id}")
        return directory


def _write_atomically(path: Path, data: bytes) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _encode_metadata(metadata: BackupMetadata) -> bytes:
    return json.dumps(
        {
            "backup_id": metadata.backup_id,
            "created_at": metadata.created_at.isoformat(),
            "memory_count": metadata.memory_count,
            "size_bytes": metadata.size_bytes,
            "collections": metadata.collections,
            "description": metadata.description,
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


def _decode_metadata(text: str) -> BackupMetadata:
    raw = json.loads(text)
    return BackupMetadata(
        backup_id=raw["backup_id"],
        created_at=datetime.fromisoformat(raw["created_at"]),
        memory_count=raw["memory_count"],
        size_bytes=raw["size_bytes"],
        collections=raw["collections"],
        description=raw.get("description"),
    )
