"""Where the server keeps each category of its persistent state, for the storage ledger.

[INPUT]
- app.config.settings::DatabaseSettings (POS: every path of the persistent state, including the relocated ones)
- app.database.operations.backup::backup_dir_for (POS: where the SQLite backup manager keeps its backups)
- myrm_agent_harness.observability.storage_governance::StorageCategory

[OUTPUT]
- build_storage_layout: category -> paths, in the form the storage inspector takes

[POS]
Business knowledge of the server's data layout. The harness inspector owns the attribution rules and measures what
it is told; this module is the one place that tells it, so a deployment that relocates memory or logs to another
volume is attributed where the data really is, and everything else in the state directory is reported as other.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.observability.storage_governance import StorageCategory

from app.config.settings import DatabaseSettings
from app.database.operations.backup import backup_dir_for

# Restore points live below the state directory, one folder per point.
_RESTORE_POINTS_SUBDIR = "snapshots"


def build_storage_layout(database: DatabaseSettings) -> dict[StorageCategory, tuple[Path, ...]]:
    """The paths of each category as the settings place them; a path that does not exist yet measures as empty."""
    sqlite_path = Path(database.sqlite_path)
    return {
        StorageCategory.SQLITE_DATABASE: (sqlite_path,),
        StorageCategory.CHECKPOINTS: (Path(database.sqlite_db_path),),
        StorageCategory.WORKSPACES: (Path(database.harness_dir),),
        StorageCategory.VECTOR_STORE: (Path(database.qdrant_path),),
        StorageCategory.MEMORY_ARCHIVE: (Path(database.memory_base_path),),
        StorageCategory.EVENT_LOGS: (Path(database.event_log_dir),),
        StorageCategory.SQLITE_BACKUPS: (backup_dir_for(sqlite_path),),
        StorageCategory.SNAPSHOTS: (Path(database.state_dir) / _RESTORE_POINTS_SUBDIR,),
    }
