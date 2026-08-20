"""Live full-stack integration test for server database startup and SchemaGate.

Validates that:
1. Server init_database successfully bootstraps tables, runs real migrations, creates indexes.
2. PRAGMA user_version is properly verified by SchemaGate in the real server database lifecycle.
3. If an incompatible future database is detected, init_database fails closed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from myrm_agent_harness.utils.db.sqlite import (
    SchemaVersionTooNewError,
    StorageCapabilities,
    validate_schema_gate_sync,
)

from app.database.connection import init_database
from app.database.migrations import MIGRATION_STATEMENTS
from app.platform_utils import reset_database_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_init_database_live_lifecycle_and_schema_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validate server init_database initializes tables and enforces SchemaGate."""
    test_db_file = tmp_path / "server_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{test_db_file}")

    # Reset any existing connection engine in the process
    await reset_database_engine()

    try:
        # 1. Run real server database initialization
        await init_database()

        # 2. Check on-disk sqlite user_version matches migration statements count
        expected_ver = len(MIGRATION_STATEMENTS) - 1
        with sqlite3.connect(str(test_db_file)) as conn:
            row = conn.execute("PRAGMA user_version").fetchone()
            assert row is not None and row[0] == expected_ver

            # Validate schema gate passes
            caps = StorageCapabilities(
                schema_version=expected_ver,
                min_compatible_version=1,
                required_tables=("chats", "messages", "agents"),
            )
            val_ver = validate_schema_gate_sync(conn, caps, db_path=test_db_file)
            assert val_ver == expected_ver

        # 3. Corrupt user_version to simulate future schema version (e.g. 9999)
        with sqlite3.connect(str(test_db_file)) as conn:
            conn.execute("PRAGMA user_version = 9999")
            conn.commit()

        # 4. Re-running init_database on a future version must fail-closed with SchemaVersionTooNewError
        with pytest.raises(SchemaVersionTooNewError) as exc_info:
            await init_database()
        assert exc_info.value.detected_version == 9999
        assert exc_info.value.expected_version == expected_ver
    finally:
        await reset_database_engine()
