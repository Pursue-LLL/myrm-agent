"""A sealed config row whose key is gone is reported as unreadable instead of looking like an empty config.

[INPUT]
app.services.config.service::ConfigService/_decrypt_with_status/_decrypt_if_needed/_encrypt_if_sensitive
app.services.config.encryption::ConfigEncryptionService

[OUTPUT]
That a row sealed under another key comes back empty AND flagged ``unreadable``, so a client can tell "nothing saved"
from "saved but cannot be opened", and that readable, plaintext and absent rows never carry the flag.

[POS]
Real ORM tables on an in-memory database; the encryption service is swapped between two local keys to simulate key loss.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import service
from app.services.config.encryption import ConfigEncryptionService
from app.services.config.service import ConfigService

_PROVIDERS = {"providers": [{"id": "openai", "apiKey": "sk-sealed-before-key-loss"}]}
_SETTINGS = {"theme": "dark"}


def _local_encryption() -> ConfigEncryptionService:
    return ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)


@pytest.fixture
async def sessions(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def original_key(monkeypatch: pytest.MonkeyPatch) -> ConfigEncryptionService:
    encryption = _local_encryption()
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)
    return encryption


def _lose_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    replacement = _local_encryption()
    monkeypatch.setattr(service, "get_encryption_service", lambda: replacement)


async def _store(sessions: async_sessionmaker[AsyncSession], key: str, value: dict[str, object]) -> None:
    stored, encrypted = service._encrypt_if_sensitive(key, value)
    db_value = {"_cipher": stored} if encrypted else value
    async with sessions() as db:
        db.add(
            UserConfig(
                id=f"id-{key}", config_key=key, config_value=db_value, is_encrypted=encrypted, version="1_0", last_device_id="d"
            )
        )
        await db.commit()


async def test_a_row_sealed_under_a_lost_key_is_empty_and_flagged_unreadable(
    sessions: async_sessionmaker[AsyncSession], original_key: ConfigEncryptionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _store(sessions, "providers", _PROVIDERS)
    _lose_the_key(monkeypatch)

    record = await ConfigService().get("providers")

    assert record is not None
    assert record.encrypted
    assert record.value == {}
    assert record.unreadable


async def test_get_all_flags_only_the_rows_that_cannot_be_opened(
    sessions: async_sessionmaker[AsyncSession], original_key: ConfigEncryptionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _store(sessions, "providers", _PROVIDERS)
    await _store(sessions, "personalSettings", _SETTINGS)
    _lose_the_key(monkeypatch)

    records = await ConfigService().get_all()

    assert records["providers"].unreadable
    assert not records["personalSettings"].unreadable
    assert records["personalSettings"].value == _SETTINGS


async def test_a_row_sealed_under_the_current_key_is_readable(
    sessions: async_sessionmaker[AsyncSession], original_key: ConfigEncryptionService
) -> None:
    await _store(sessions, "providers", _PROVIDERS)

    record = await ConfigService().get("providers")

    assert record is not None
    assert record.value == _PROVIDERS
    assert not record.unreadable


async def test_a_saved_empty_sealed_value_is_not_mistaken_for_a_lost_key(
    sessions: async_sessionmaker[AsyncSession], original_key: ConfigEncryptionService
) -> None:
    await _store(sessions, "providers", {})

    record = await ConfigService().get("providers")

    assert record is not None
    assert record.value == {}
    assert not record.unreadable


async def test_the_flag_is_serialized_for_clients_and_cleared_by_a_fresh_write(
    sessions: async_sessionmaker[AsyncSession], original_key: ConfigEncryptionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _store(sessions, "providers", _PROVIDERS)
    _lose_the_key(monkeypatch)
    unreadable = await ConfigService().get("providers")
    assert unreadable is not None
    assert unreadable.model_dump(by_alias=True)["unreadable"] is True

    written = await ConfigService().set(
        "providers", {"providers": [{"id": "fresh"}]}, device_id="d", expected_version=unreadable.version
    )
    reread = await ConfigService().get("providers")

    assert not written.unreadable
    assert reread is not None
    assert not reread.unreadable
    assert reread.value == {"providers": [{"id": "fresh"}]}


def test_the_decrypt_helper_reports_unreadable_without_changing_the_value_wrapper(
    original_key: ConfigEncryptionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored, _ = service._encrypt_if_sensitive("providers", _PROVIDERS)
    row = UserConfig(config_key="providers", config_value={"_cipher": stored}, is_encrypted=True)

    assert service._decrypt_with_status(row) == (_PROVIDERS, False)
    assert service._decrypt_if_needed(row) == _PROVIDERS

    _lose_the_key(monkeypatch)

    assert service._decrypt_with_status(row) == ({}, True)
    assert service._decrypt_if_needed(row) == {}
