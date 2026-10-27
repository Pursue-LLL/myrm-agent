"""The startup migration that encrypts plaintext sensitive rows must leave rows the config service can read."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import UserConfig
from app.services.config import migration, service
from app.services.config.encryption import ConfigEncryptionService

_AGENTS = {"agents": [{"name": "claude", "env": {"HTTPS_PROXY": "http://user:proxy-secret@proxy.example:8080"}}]}


@pytest.fixture(autouse=True)
def local_encryption(monkeypatch: pytest.MonkeyPatch) -> ConfigEncryptionService:
    """A local-mode encryption service with its own key, so no machine key file is read."""
    encryption = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: encryption)
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)
    return encryption


@pytest.fixture
async def sessions() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _row(key: str, value: object, *, encrypted: bool = False) -> UserConfig:
    return UserConfig(
        id=f"id-{key}", config_key=key, config_value=value, is_encrypted=encrypted, version="1_0", last_device_id="device"
    )


async def _stored(sessions: async_sessionmaker[AsyncSession], key: str) -> UserConfig:
    async with sessions() as db:
        return (await db.execute(select(UserConfig).where(UserConfig.config_key == key))).scalar_one()


async def test_a_migrated_row_is_flagged_so_the_service_reads_back_what_was_stored(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as db:
        db.add(_row("externalAgents", _AGENTS))
        await db.commit()

    async with sessions() as db:
        stats = await migration.migrate_configs_to_encrypted(db)

    stored = await _stored(sessions, "externalAgents")
    assert stats == {"migrated": 1, "skipped": 0, "errors": 0}
    assert stored.is_encrypted is True
    assert "proxy-secret" not in str(stored.config_value)
    assert service._decrypt_if_needed(stored) == _AGENTS


async def test_rows_already_encrypted_and_rows_that_are_not_secret_are_left_as_they_are(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    sealed, flagged = service._encrypt_if_sensitive("providers", {"openai": "sk-kept"})
    assert flagged
    async with sessions() as db:
        db.add_all(
            [
                _row("providers", sealed, encrypted=True),
                _row("personalSettings", {"theme": "dark"}),
                _row("externalAgents", _AGENTS),
            ]
        )
        await db.commit()

    async with sessions() as db:
        stats = await migration.migrate_configs_to_encrypted(db)

    assert stats == {"migrated": 1, "skipped": 2, "errors": 0}
    assert service._decrypt_if_needed(await _stored(sessions, "providers")) == {"openai": "sk-kept"}
    assert service._decrypt_if_needed(await _stored(sessions, "personalSettings")) == {"theme": "dark"}
    assert service._decrypt_if_needed(await _stored(sessions, "externalAgents")) == _AGENTS


async def test_a_row_saved_by_the_config_service_is_not_sealed_a_second_time(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    sealed, flagged = service._encrypt_if_sensitive("providers", {"openai": "sk-kept"})
    assert flagged
    envelope = {"_cipher": sealed}
    async with sessions() as db:
        db.add(_row("providers", envelope, encrypted=True))
        await db.commit()

    async with sessions() as db:
        stats = await migration.migrate_configs_to_encrypted(db)

    stored = await _stored(sessions, "providers")
    assert stats == {"migrated": 0, "skipped": 1, "errors": 0}
    assert stored.config_value == envelope
    assert service._decrypt_if_needed(stored) == {"openai": "sk-kept"}


async def test_a_second_run_changes_nothing(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as db:
        db.add(_row("externalAgents", _AGENTS))
        await db.commit()
    async with sessions() as db:
        await migration.migrate_configs_to_encrypted(db)
    first = (await _stored(sessions, "externalAgents")).config_value

    async with sessions() as db:
        stats = await migration.migrate_configs_to_encrypted(db)

    assert stats == {"migrated": 0, "skipped": 1, "errors": 0}
    assert (await _stored(sessions, "externalAgents")).config_value == first


def test_the_list_of_external_agents_is_stored_encrypted_like_the_other_secret_rows(
    local_encryption: ConfigEncryptionService,
) -> None:
    assert local_encryption.should_encrypt("externalAgents")

    stored, encrypted = service._encrypt_if_sensitive("externalAgents", _AGENTS)

    assert encrypted and "proxy-secret" not in str(stored)
