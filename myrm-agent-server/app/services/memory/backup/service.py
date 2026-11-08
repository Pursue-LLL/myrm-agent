"""Local memory backup orchestration.

[INPUT]
app.services.memory.backup.snapshot::capture_snapshot/apply_snapshot/SnapshotError (POS: 备份快照契约)
app.services.memory.backup.volume_store::VolumeBackupStore (POS: 持久卷存储)

[OUTPUT]
MemoryBackupService

[POS]
本地备份的创建与恢复流程：把 MemoryManager 与 VolumeBackupStore 串起来。覆盖式恢复会先把当前记忆另存为一份新备份，
任何一步失败都不会让用户失去数据副本。手动创建在旧嵌入模型下仍有记忆时被拒绝，覆盖式恢复的安全副本不受此限。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.backup import BackupMetadata

from app.services.memory.backup.snapshot import SnapshotError, apply_snapshot, capture_snapshot
from app.services.memory.backup.volume_store import VolumeBackupStore

logger = logging.getLogger(__name__)

PRE_RESTORE_DESCRIPTION: Final = "Automatic backup before restore"


class MemoryBackupService:
    def __init__(self, manager: MemoryManager, store: VolumeBackupStore) -> None:
        self._manager = manager
        self._store = store

    async def create(self, description: str | None = None, *, allow_previous_models: bool = False) -> BackupMetadata:
        """Save a backup of every memory; refuses while memories sit under a previous embedding model.

        ``allow_previous_models`` saves what the current model sees instead (see ``capture_snapshot``).
        """
        snapshot = await capture_snapshot(self._manager, allow_previous_models=allow_previous_models)
        return await asyncio.to_thread(self._store.save, snapshot, description)

    async def restore(self, backup_id: str, *, overwrite: bool) -> int:
        """Restore a backup and return how many memories were written.

        The backup is decoded before anything is touched, so a missing or corrupt file never
        costs the user existing memories.
        """
        snapshot = await asyncio.to_thread(self._store.load, backup_id)
        if not overwrite:
            return sum((await apply_snapshot(self._manager, snapshot, replace=False)).values())

        # A replacing restore leaves memories under a previous model untouched, so the copy of what it replaces
        # is complete without them and must not be held back by them.
        safety_copy = await self.create(PRE_RESTORE_DESCRIPTION, allow_previous_models=True)
        try:
            counts = await apply_snapshot(self._manager, snapshot, replace=True)
        except SnapshotError as exc:
            raise SnapshotError(f"{exc}; previous memories are saved as backup {safety_copy.backup_id}") from exc
        except Exception as exc:
            logger.exception("Memory restore failed after saving safety backup %s", safety_copy.backup_id)
            raise SnapshotError(f"Restore failed; previous memories are saved as backup {safety_copy.backup_id}") from exc
        return sum(counts.values())
