"""The startup sweep seals what was saved in plaintext, in a sandbox as well as on a local machine.

[INPUT]
app.services.config.migration::seal_stored_configs
app.services.config.encryption::ConfigEncryptionService
app.services.config.service::_decrypt_if_needed/_decrypt_audit_log_value

[OUTPUT]
That a sandbox (its key comes from the control plane) seals the secret rows and the history it saved earlier and still
reads them back, and that a mode that does not encrypt configs is left exactly as it was.

[POS]
Real ORM tables on an in-memory database; only the session factory and the encryption service are injected.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.deploy_mode import DeployMode
from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import migration, service
from app.services.config.encryption import ConfigEncryptionService

_VOICE = {"sttApiKey": "sk-stt-secret", "ttsApiKey": "sk-tts-secret"}
_BACKUP = {"enabled": True, "provider": "s3", "s3": {"secretAccessKey": "s3-secret"}}
_PREFERENCES = {"theme": "dark"}


@pytest.fixture
async def sessions(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession]:
        async with factory() as db:
            yield db

    monkeypatch.setattr("app.database.connection.get_session", session)
    async with factory() as db:
        for key, value in (("voice", _VOICE), ("backupSync", _BACKUP), ("chatSettings", _PREFERENCES)):
            db.add(
                UserConfig(
                    id=f"id-{key}", config_key=key, config_value=value, is_encrypted=False, version="1_0", last_device_id="d"
                )
            )
        db.add(
            ConfigAuditLog(id="history", config_key="voice", previous_value=None, new_value=_VOICE, version="1_0", device_id="d")
        )
        await db.commit()
    yield factory
    await engine.dispose()


def _use(monkeypatch: pytest.MonkeyPatch, encryption: ConfigEncryptionService) -> None:
    monkeypatch.setattr(migration, "get_encryption_service", lambda: encryption)
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)


async def _row(sessions: async_sessionmaker[AsyncSession], key: str) -> UserConfig:
    async with sessions() as db:
        return (await db.execute(select(UserConfig).where(UserConfig.config_key == key))).scalar_one()


async def test_a_sandbox_seals_the_rows_and_the_history_it_saved_before(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.deploy_mode.get_deploy_mode", lambda: DeployMode.SANDBOX)
    _use(monkeypatch, ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=True, is_local=False))

    await migration.seal_stored_configs()

    voice, backup, preferences = (
        await _row(sessions, "voice"),
        await _row(sessions, "backupSync"),
        await _row(sessions, "chatSettings"),
    )
    assert voice.is_encrypted and backup.is_encrypted
    assert "sk-stt-secret" not in str(voice.config_value) and "s3-secret" not in str(backup.config_value)
    assert service._decrypt_if_needed(voice) == _VOICE
    assert service._decrypt_if_needed(backup) == _BACKUP
    assert not preferences.is_encrypted and preferences.config_value == _PREFERENCES
    async with sessions() as db:
        history = (await db.execute(select(ConfigAuditLog))).scalar_one()
    assert "sk-stt-secret" not in str(history.new_value)
    assert service._decrypt_audit_log_value("voice", history.new_value) == _VOICE


async def test_a_mode_that_does_not_encrypt_configs_is_left_exactly_as_it_was(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, ConfigEncryptionService(encryption_key=None, is_sandbox=False, is_local=False))

    await migration.seal_stored_configs()

    voice = await _row(sessions, "voice")
    assert not voice.is_encrypted
    assert voice.config_value == _VOICE
