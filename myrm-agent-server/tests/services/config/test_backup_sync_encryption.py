"""The remote backup settings hold the WebDAV password and the S3 secret key, so they are stored like every other secret row.

[INPUT]
app.services.config.encryption::ConfigEncryptionService/is_sensitive_config
app.services.config.migration::migrate_configs_to_encrypted/migrate_config_history_to_encrypted
app.services.config.service::_decrypt_if_needed/_decrypt_audit_log_value/_encrypt_if_sensitive

[OUTPUT]
That ``backupSync`` is encrypted at rest, that a row saved before it was sensitive is sealed and still readable after
the startup migration, and that the plaintext copies the audit history kept of it (and of any sensitive key) are sealed too.

[POS]
Real ORM tables on an in-memory database and a local-mode encryption service with its own key.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import migration, service
from app.services.config.encryption import ConfigEncryptionService, is_sensitive_config

_OLD = {"enabled": True, "provider": "webdav", "webdav": {"host": "https://dav.example", "password": "old-dav-secret"}}
_NEW = {"enabled": True, "provider": "s3", "s3": {"bucket": "vault", "secretAccessKey": "new-s3-secret"}}


@pytest.fixture(autouse=True)
def local_encryption(monkeypatch: pytest.MonkeyPatch) -> ConfigEncryptionService:
    encryption = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: encryption)
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)
    return encryption


@pytest.fixture
async def sessions() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _config(key: str, value: object) -> UserConfig:
    return UserConfig(id=f"id-{key}", config_key=key, config_value=value, is_encrypted=False, version="1_0", last_device_id="d")


def _audit(row_id: str, key: str, previous: object, new: object) -> ConfigAuditLog:
    return ConfigAuditLog(id=row_id, config_key=key, previous_value=previous, new_value=new, version="1_0", device_id="d")


async def _audit_row(sessions: async_sessionmaker[AsyncSession], row_id: str) -> ConfigAuditLog:
    async with sessions() as db:
        return (await db.execute(select(ConfigAuditLog).where(ConfigAuditLog.id == row_id))).scalar_one()


def test_the_remote_backup_settings_are_stored_encrypted(local_encryption: ConfigEncryptionService) -> None:
    assert is_sensitive_config("backupSync")

    stored, encrypted = service._encrypt_if_sensitive("backupSync", _NEW)

    assert encrypted
    assert "new-s3-secret" not in str(stored)


async def test_remote_backup_settings_saved_in_plaintext_are_sealed_and_still_read_back(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as db:
        db.add(_config("backupSync", _OLD))
        await db.commit()

    async with sessions() as db:
        stats = await migration.migrate_configs_to_encrypted(db)

    async with sessions() as db:
        stored = (await db.execute(select(UserConfig).where(UserConfig.config_key == "backupSync"))).scalar_one()
    assert stats["migrated"] == 1
    assert "old-dav-secret" not in str(stored.config_value)
    assert service._decrypt_if_needed(stored) == _OLD


async def test_the_plaintext_history_of_a_sensitive_key_is_sealed_and_still_decrypts(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as db:
        db.add(_audit("first", "backupSync", None, _OLD))
        db.add(_audit("second", "backupSync", _OLD, _NEW))
        await db.commit()

    async with sessions() as db:
        sealed = await migration.migrate_config_history_to_encrypted(db)

    first, second = await _audit_row(sessions, "first"), await _audit_row(sessions, "second")
    assert sealed == 3
    assert first.previous_value is None
    assert "dav-secret" not in str((first.new_value, second.previous_value, second.new_value))
    assert service._decrypt_audit_log_value("backupSync", first.new_value) == _OLD
    assert service._decrypt_audit_log_value("backupSync", second.previous_value) == _OLD
    assert service._decrypt_audit_log_value("backupSync", second.new_value) == _NEW


async def test_history_that_is_already_sealed_or_not_secret_is_left_alone_and_a_second_run_changes_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    sealed_value, _ = service._encrypt_if_sensitive("providers", {"openai": "sk-kept"})
    already_sealed = {"_cipher": sealed_value}
    async with sessions() as db:
        db.add(_audit("sealed", "providers", None, already_sealed))
        db.add(_audit("bare", "providers", sealed_value, already_sealed))  # a row migrated from plaintext keeps a bare string
        db.add(_audit("plain", "personalSettings", {"theme": "dark"}, {"theme": "light"}))
        db.add(_audit("secret", "backupSync", None, _OLD))
        await db.commit()

    async with sessions() as db:
        first_run = await migration.migrate_config_history_to_encrypted(db)
    async with sessions() as db:
        second_run = await migration.migrate_config_history_to_encrypted(db)

    assert (first_run, second_run) == (1, 0)
    assert (await _audit_row(sessions, "sealed")).new_value == already_sealed
    bare = await _audit_row(sessions, "bare")
    assert (bare.previous_value, bare.new_value) == (sealed_value, already_sealed)
    plain = await _audit_row(sessions, "plain")
    assert (plain.previous_value, plain.new_value) == ({"theme": "dark"}, {"theme": "light"})
    assert service._decrypt_audit_log_value("backupSync", (await _audit_row(sessions, "secret")).new_value) == _OLD


async def test_a_mode_that_stores_secrets_in_plaintext_leaves_the_history_as_it_is(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    idle = ConfigEncryptionService(encryption_key=None, is_sandbox=False, is_local=False)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: idle)
    async with sessions() as db:
        db.add(_audit("secret", "backupSync", None, _OLD))
        await db.commit()

    async with sessions() as db:
        assert await migration.migrate_config_history_to_encrypted(db) == 0

    assert (await _audit_row(sessions, "secret")).new_value == _OLD
