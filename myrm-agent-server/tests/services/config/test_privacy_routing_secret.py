"""The key of the user's own model endpoint lives in a sealed row of its own, never in the preferences.

[INPUT]
app.services.config.migration::seal_stored_configs
app.services.config.service::ConfigService (POS: the one writer of config rows and their audit history)
app.services.config.encryption::ConfigEncryptionService

[OUTPUT]
That a key saved through the service is sealed in the row and in its history, that the startup sweep carries a key an
older build saved inside ``personalSettings`` into that row and removes it from the row and from every snapshot of it,
and that a second sweep, a stale field, a failure and a different master key each leave the stored data as they should.

[POS]
Real ORM tables on an in-memory database and the real ``ConfigService`` writer; only the session factory and the
encryption service are injected.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import migration, service
from app.services.config.encryption import ConfigEncryptionService

_KEY = "privacyRoutingSecret"
_SECRET = "sk-gateway-secret-current"
_ROTATED_OUT = "sk-gateway-secret-rotated-out"
_STALE = "sk-gateway-secret-stale-field"
_ROUTING = {"localModel": "ollama/qwen2.5", "localBaseUrl": "http://gateway.internal:11434"}


@pytest.fixture
def encryption(monkeypatch: pytest.MonkeyPatch) -> ConfigEncryptionService:
    sealing = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: sealing)
    monkeypatch.setattr(service, "get_encryption_service", lambda: sealing)
    return sealing


@pytest.fixture
async def sessions(
    encryption: ConfigEncryptionService, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
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
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


async def _save_preferences(*, key: str | None, theme: str, expected_version: str | None = None) -> str:
    """Save the preferences the way an older build did: the key sits inside ``privacyRouting``."""
    routing = {**_ROUTING, "localApiKey": key} if key is not None else dict(_ROUTING)
    record = await service.ConfigService().set(
        "personalSettings", {"privacyRouting": routing, "theme": theme}, "browser", expected_version=expected_version
    )
    return record.version


async def _plaintext_everywhere(sessions: async_sessionmaker[AsyncSession]) -> str:
    """Every stored config value and every audit snapshot, as the text a copy of the database would contain."""
    async with sessions() as db:
        rows = (await db.execute(select(UserConfig))).scalars().all()
        logs = (await db.execute(select(ConfigAuditLog))).scalars().all()
    return "\n".join([str(row.config_value) for row in rows] + [f"{log.previous_value}|{log.new_value}" for log in logs])


async def _row(sessions: async_sessionmaker[AsyncSession], key: str) -> UserConfig | None:
    async with sessions() as db:
        return (await db.execute(select(UserConfig).where(UserConfig.config_key == key))).scalar_one_or_none()


async def _stored(sessions: async_sessionmaker[AsyncSession]) -> list[tuple[str, str, bool, str]]:
    async with sessions() as db:
        rows = (await db.execute(select(UserConfig).order_by(UserConfig.config_key))).scalars().all()
    return [(row.config_key, str(row.config_value), row.is_encrypted, row.version) for row in rows]


async def test_a_key_saved_through_the_service_is_sealed_in_the_row_and_in_its_history(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    saved = await service.ConfigService().set(_KEY, {"localApiKey": _SECRET}, "browser")
    await service.ConfigService().set(_KEY, {"localApiKey": _ROTATED_OUT}, "browser", expected_version=saved.version)

    row = await _row(sessions, _KEY)

    assert row is not None and row.is_encrypted
    text = await _plaintext_everywhere(sessions)
    assert _SECRET not in text and _ROTATED_OUT not in text
    read_back = await service.ConfigService().get(_KEY)
    assert read_back is not None and read_back.value == {"localApiKey": _ROTATED_OUT}


async def test_the_sweep_moves_a_key_saved_in_the_preferences_into_the_sealed_row(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    version_before = await _save_preferences(key=_SECRET, theme="dark")

    await migration.seal_stored_configs()

    secret = await _row(sessions, _KEY)
    assert secret is not None and secret.is_encrypted
    assert service._decrypt_if_needed(secret) == {"localApiKey": _SECRET}
    preferences = await service.ConfigService().get("personalSettings")
    assert preferences is not None
    assert preferences.value == {"privacyRouting": _ROUTING, "theme": "dark"}
    assert preferences.version != version_before
    assert _SECRET not in await _plaintext_everywhere(sessions)


async def test_no_snapshot_of_the_preferences_keeps_a_key_that_was_ever_saved(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await _save_preferences(key=_ROTATED_OUT, theme="dark")
    await _save_preferences(key=_SECRET, theme="light", expected_version=first)

    await migration.seal_stored_configs()

    text = await _plaintext_everywhere(sessions)
    assert _ROTATED_OUT not in text and _SECRET not in text
    async with sessions() as db:
        logs = (await db.execute(select(ConfigAuditLog).where(ConfigAuditLog.config_key == "personalSettings"))).scalars().all()
    assert len(logs) == 2
    assert sorted(str(log.new_value["theme"]) for log in logs) == ["dark", "light"]
    assert all(log.new_value["privacyRouting"] == _ROUTING for log in logs)
    assert all(log.previous_value is None or log.previous_value["privacyRouting"] == _ROUTING for log in logs)


async def test_a_key_that_was_cleared_before_the_sweep_leaves_no_row_and_no_trace(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await _save_preferences(key=_ROTATED_OUT, theme="dark")
    await _save_preferences(key=None, theme="dark", expected_version=first)

    await migration.seal_stored_configs()

    assert await _row(sessions, _KEY) is None
    assert _ROTATED_OUT not in await _plaintext_everywhere(sessions)


async def test_an_empty_key_field_is_removed_without_creating_a_row(sessions: async_sessionmaker[AsyncSession]) -> None:
    await _save_preferences(key="", theme="dark")

    await migration.seal_stored_configs()

    assert await _row(sessions, _KEY) is None
    preferences = await service.ConfigService().get("personalSettings")
    assert preferences is not None and preferences.value["privacyRouting"] == _ROUTING


async def test_a_second_sweep_changes_nothing(sessions: async_sessionmaker[AsyncSession]) -> None:
    await _save_preferences(key=_SECRET, theme="dark")
    await migration.seal_stored_configs()
    after_first = await _stored(sessions)
    text_after_first = await _plaintext_everywhere(sessions)

    await migration.seal_stored_configs()

    assert await _stored(sessions) == after_first
    assert await _plaintext_everywhere(sessions) == text_after_first


async def test_preferences_that_never_held_a_key_are_not_touched(sessions: async_sessionmaker[AsyncSession]) -> None:
    await _save_preferences(key=None, theme="dark")
    before = await _stored(sessions)

    await migration.seal_stored_configs()

    assert await _stored(sessions) == before
    assert await _row(sessions, _KEY) is None


async def test_a_sealed_row_that_already_exists_wins_over_a_stale_field(sessions: async_sessionmaker[AsyncSession]) -> None:
    await service.ConfigService().set(_KEY, {"localApiKey": _SECRET}, "browser")
    await _save_preferences(key=_STALE, theme="dark")

    await migration.seal_stored_configs()

    secret = await _row(sessions, _KEY)
    assert secret is not None
    assert service._decrypt_if_needed(secret) == {"localApiKey": _SECRET}
    assert _STALE not in await _plaintext_everywhere(sessions)


async def test_a_failed_move_leaves_the_stored_key_where_it_was(
    sessions: async_sessionmaker[AsyncSession], encryption: ConfigEncryptionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _save_preferences(key=_SECRET, theme="dark")
    before = await _stored(sessions)

    def refuse(config_key: str, value: dict[str, object]) -> tuple[dict[str, object] | str, bool]:
        raise RuntimeError("sealing is unavailable")

    monkeypatch.setattr(encryption, "encrypt_if_needed", refuse)

    with pytest.raises(RuntimeError, match="sealing is unavailable"):
        await migration.seal_stored_configs()

    assert await _stored(sessions) == before
    assert await _row(sessions, _KEY) is None


async def test_a_different_master_key_neither_rewrites_the_sealed_row_nor_touches_the_preferences(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _save_preferences(key=_SECRET, theme="dark")
    await migration.seal_stored_configs()
    sealed_with_the_first_key = await _stored(sessions)

    other = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: other)
    monkeypatch.setattr(service, "get_encryption_service", lambda: other)
    await migration.seal_stored_configs()

    assert await _stored(sessions) == sealed_with_the_first_key
    unreadable = await service.ConfigService().get(_KEY)
    assert unreadable is not None and unreadable.value == {}
    preferences = await service.ConfigService().get("personalSettings")
    assert preferences is not None and preferences.value["privacyRouting"] == _ROUTING


async def test_a_mode_that_cannot_seal_still_keeps_the_key_out_of_the_preferences(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    unsealed = ConfigEncryptionService(encryption_key=None, is_sandbox=False, is_local=False)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: unsealed)
    monkeypatch.setattr(service, "get_encryption_service", lambda: unsealed)
    await _save_preferences(key=_SECRET, theme="dark")

    await migration.seal_stored_configs()

    secret = await _row(sessions, _KEY)
    assert secret is not None and not secret.is_encrypted
    assert secret.config_value == {"localApiKey": _SECRET}
    preferences = await service.ConfigService().get("personalSettings")
    assert preferences is not None and "localApiKey" not in preferences.value["privacyRouting"]
