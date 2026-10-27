"""A first-time install is reported as "nothing configured yet", not as a failed configuration load.

[INPUT]
app.api.config.router::get_config_readiness
app.core.channel_bridge.config_readiness::load_readiness_inputs (via the route)
app.services.config.service::config_service (decrypts the stored provider bundle)

[OUTPUT]
That a fresh database, providers without a default model, and providers sealed under a lost key each come back as a
normal "provider not ready" answer with the onboarding flag read from the database, while a real load failure is still
reported as degraded.

[POS]
Real ORM table on an in-memory database behind the real route function; the model resolver is the production one.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.config.router import get_config_readiness
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import service
from app.services.config.encryption import ConfigEncryptionService

_PROVIDER = {
    "id": "openai",
    "name": "openai",
    "routingProfile": "openai",
    "isBuiltIn": False,
    "isEnabled": True,
    "apiUrl": "https://api.openai.com/v1",
    "apiKeys": [{"key": "sk-readiness-test", "isActive": True}],
    "enabledModels": ["gpt-4o"],
    "availableModels": ["gpt-4o"],
    "providerType": "openai",
}
_DEFAULT_MODEL = {
    "baseModel": {
        "primary": {"providerId": "openai", "model": "gpt-4o"},
        "fallback": None,
        "temperature": 0.7,
        "modelKwargs": {},
    },
    "liteModel": None,
    "fastModeModel": None,
    "routingConfig": None,
    "visionFallbackModel": None,
}


def _local_encryption() -> ConfigEncryptionService:
    return ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)


@pytest.fixture
async def sessions(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    encryption = _local_encryption()
    monkeypatch.setattr("app.database.connection.get_session", get_session)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)
    monkeypatch.setattr("app.services.config.encryption.get_encryption_service", lambda: encryption)
    invalidate_user_configs_cache()
    yield factory
    invalidate_user_configs_cache()
    await engine.dispose()


async def _store(sessions: async_sessionmaker[AsyncSession], key: str, value: dict[str, object]) -> None:
    stored, encrypted = service._encrypt_if_sensitive(key, value)
    db_value = {"_cipher": stored} if encrypted else value
    async with sessions() as db:
        db.add(
            UserConfig(
                id=f"id-{key}",
                config_key=key,
                config_value=db_value,
                is_encrypted=encrypted,
                version="1_0",
                last_device_id="d",
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def test_a_fresh_install_is_not_ready_but_not_degraded_and_still_gets_onboarding(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    readiness = await get_config_readiness()

    assert readiness["degraded"] is False
    assert readiness["onboarding_completed"] is False
    assert readiness["provider"]["is_ready"] is False
    assert readiness["provider"]["missing_items"] == ["providers"]


async def test_an_installation_that_finished_onboarding_without_a_provider_keeps_that_answer(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _store(sessions, "onboarding", {"completed_at": "2026-10-01T00:00:00+00:00"})

    readiness = await get_config_readiness()

    assert readiness["degraded"] is False
    assert readiness["onboarding_completed"] is True
    assert readiness["provider"]["missing_items"] == ["providers"]


async def test_providers_saved_without_a_default_model_are_judged_by_the_provider_check(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _store(sessions, "providers", {"providers": [_PROVIDER]})

    readiness = await get_config_readiness()

    assert readiness["degraded"] is False
    assert readiness["provider"]["is_ready"] is True


async def test_a_configured_install_is_ready(sessions: async_sessionmaker[AsyncSession]) -> None:
    await _store(sessions, "providers", {"providers": [_PROVIDER], "defaultModelConfig": _DEFAULT_MODEL})

    readiness = await get_config_readiness()

    assert readiness["degraded"] is False
    assert readiness["provider"]["is_ready"] is True


async def test_providers_sealed_under_a_lost_key_read_as_not_configured_instead_of_degraded(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    await _store(sessions, "providers", {"providers": [_PROVIDER], "defaultModelConfig": _DEFAULT_MODEL})
    replacement = _local_encryption()
    monkeypatch.setattr(service, "get_encryption_service", lambda: replacement)
    monkeypatch.setattr("app.services.config.encryption.get_encryption_service", lambda: replacement)

    readiness = await get_config_readiness()

    assert readiness["degraded"] is False
    assert readiness["provider"]["is_ready"] is False
    assert readiness["provider"]["missing_items"] == ["providers"]


async def test_a_real_load_failure_is_still_reported_as_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(side_effect=RuntimeError("database locked"))
    )

    readiness = await get_config_readiness()

    assert readiness["degraded"] is True
    assert readiness["provider"]["missing_items"] == ["config_load_failed"]
    assert readiness["onboarding_completed"] is True
