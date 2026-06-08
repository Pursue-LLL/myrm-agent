"""Tests for pre-migration safety snapshot in init_database().

Verifies that backup_database() is called before run_migrations()
to protect multi-step DDL migrations from partial failure.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_init_database_calls_backup_before_migrations():
    """backup_database() must execute before run_migrations()."""
    call_order: list[str] = []

    def fake_backup(path: str) -> None:
        call_order.append("backup")

    async def fake_run_migrations(engine: object) -> None:
        call_order.append("migrations")

    async def fake_create_indexes(engine: object) -> None:
        call_order.append("indexes")

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.recovery.backup_database", side_effect=fake_backup),
        patch("app.config.settings.settings") as mock_settings,
    ):
        mock_settings.database.sqlite_path = "/tmp/test.db"

        from app.database.connection import init_database

        await init_database()

    assert "backup" in call_order, "backup_database was not called"
    assert "migrations" in call_order, "run_migrations was not called"
    backup_idx = call_order.index("backup")
    migrations_idx = call_order.index("migrations")
    assert backup_idx < migrations_idx, (
        f"backup must run before migrations, got order: {call_order}"
    )


@pytest.mark.asyncio
async def test_init_database_continues_when_backup_fails():
    """If backup_database() raises, init_database() must still proceed."""
    migrations_ran = False

    async def fake_run_migrations(engine: object) -> None:
        nonlocal migrations_ran
        migrations_ran = True

    async def fake_create_indexes(engine: object) -> None:
        pass

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.recovery.backup_database", side_effect=OSError("disk full")),
        patch("app.config.settings.settings") as mock_settings,
    ):
        mock_settings.database.sqlite_path = "/tmp/test.db"

        from app.database.connection import init_database

        await init_database()

    assert migrations_ran, "run_migrations must execute even when backup fails"
