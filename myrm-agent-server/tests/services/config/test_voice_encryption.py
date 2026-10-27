"""The voice settings hold the speech-to-text and text-to-speech API keys, so they are stored like every other secret row.

[INPUT]
app.services.config.encryption::ConfigEncryptionService/is_sensitive_config
app.services.config.migration::migrate_configs_to_encrypted/migrate_config_history_to_encrypted
app.services.config.service::_decrypt_if_needed/_encrypt_if_sensitive

[OUTPUT]
That ``voice`` is encrypted at rest, that a row saved before it was sensitive is sealed and still readable after the
startup migration, and that the plaintext copy the audit history kept of an earlier value is sealed too.

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

_VOICE = {"sttApiKey": "sk-stt-secret", "ttsApiKey": "sk-tts-secret", "ttsVoice": "alloy"}


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


def test_the_voice_settings_are_stored_encrypted() -> None:
    assert is_sensitive_config("voice")

    stored, encrypted = service._encrypt_if_sensitive("voice", _VOICE)

    assert encrypted
    assert "sk-stt-secret" not in str(stored)
    assert "sk-tts-secret" not in str(stored)


async def test_voice_settings_saved_in_plaintext_are_sealed_and_still_read_back(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as db:
        db.add(
            UserConfig(
                id="id-voice", config_key="voice", config_value=_VOICE, is_encrypted=False, version="1_0", last_device_id="d"
            )
        )
        db.add(
            ConfigAuditLog(id="first", config_key="voice", previous_value=None, new_value=_VOICE, version="1_0", device_id="d")
        )
        await db.commit()

    async with sessions() as db:
        stats = await migration.migrate_configs_to_encrypted(db)
        sealed = await migration.migrate_config_history_to_encrypted(db)

    async with sessions() as db:
        stored = (await db.execute(select(UserConfig).where(UserConfig.config_key == "voice"))).scalar_one()
        history = (await db.execute(select(ConfigAuditLog).where(ConfigAuditLog.id == "first"))).scalar_one()
    assert stats["migrated"] == 1
    assert sealed == 1
    assert "sk-stt-secret" not in str(stored.config_value)
    assert "sk-stt-secret" not in str(history.new_value)
    assert service._decrypt_if_needed(stored) == _VOICE
    assert service._decrypt_audit_log_value("voice", history.new_value) == _VOICE
