"""[INPUT]
- app.database.operations.recovery::reports_corruption/database_is_damaged/rescue_database (POS: corruption evidence and row-level salvage)
- app.database.operations.backup::get_sqlite_backup_manager (POS: integrity-verified snapshot restore)
- app.database.connection::init_database (POS: schema creation, migrations and indexes, retried after a repair)
- app.platform_utils::reset_database_engine (POS: drops the pooled engine so a repaired file is reopened)
- app.server.status::system_status (POS: recovery flags the health endpoints report)
- .state (POS: shared startup state)

[OUTPUT]
- recover_failed_init: the startup answer to a failed database initialisation

[POS]
What startup does after init_database() fails. A file with no sign of damage is left exactly as it is and the original
error ends startup; a damaged or missing one goes through salvage, snapshot restore and, last, an in-memory database.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .state import logger


async def recover_failed_init(init_error: Exception) -> None:
    """Repair the database after its initialisation failed, or re-raise ``init_error`` for an intact file.

    Salvage rewrites the file: it drops the schema version, loses the tables it cannot read, and the next call
    replaces the isolated original. The file counts as damaged when the failed start met a SQLite corruption report
    or when it fails the integrity probe. Anything else (a migration error, a schema newer than this build, a lock)
    is not repaired by salvage, so the file stays untouched and the real error surfaces. A missing file has nothing
    to damage and goes on to the snapshot restore.
    """
    from app.config.settings import settings
    from app.database.connection import init_database
    from app.database.operations.recovery import database_is_damaged, reports_corruption, rescue_database
    from app.platform_utils import reset_database_engine
    from app.server.status import system_status

    db_path = settings.database.sqlite_path

    if Path(db_path).is_file() and not (reports_corruption(init_error) or await asyncio.to_thread(database_is_damaged, db_path)):
        logger.error("[Startup] The database file shows no sign of damage: no repair was attempted and it is untouched")
        raise init_error

    # 1. Try B-Tree page-skipping rowid salvage rescue (last-resort row-level data salvage)
    if rescue_database(db_path):
        system_status.database_recovered = True
        await reset_database_engine()
        await init_database()
        logger.info("[Startup] Database rescued successfully")
        return

    # 2. Try multi-snapshot integrity-verified restore
    restored = False
    try:
        from app.database.operations.backup import get_sqlite_backup_manager

        manager = get_sqlite_backup_manager()
        if manager is not None:
            result = manager.restore_latest()
            if result.restored:
                await reset_database_engine()
                await init_database()
                restored = True
                system_status.database_recovered = True
                logger.info("[Startup] Database restored from snapshot %s", result.snapshot_file)
    except Exception as restore_exc:
        logger.warning("[Startup] Snapshot restore failed: %s", restore_exc)

    # 3. Degrade to in-memory as ultimate fallback
    if not restored:
        logger.warning("[Startup] All recovery methods exhausted, degrading to in-memory mode")
        system_status.database_degraded = True
        settings.database.sqlite_path = ":memory:"
        await reset_database_engine()
        await init_database()
