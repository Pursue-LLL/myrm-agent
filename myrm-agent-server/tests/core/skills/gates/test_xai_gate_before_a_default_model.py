"""The skills catalog lists on an install that has no default model yet instead of failing.

[INPUT]
app.core.skills.gates.oauth_availability::apply_integration_oauth_availability (real xAI provider check)
app.core.channel_bridge.config_readiness::load_readiness_inputs (reads the stored provider bundle)
app.services.config.service::config_service (decrypts the stored provider bundle)

[OUTPUT]
That a fresh install gets x-live-search marked unavailable, and that an xAI provider saved before any default model
keeps it available, both without an error from the config loader that refuses to answer without a default model.

[POS]
Real ORM table on an in-memory database; the provider check itself is the production one (the sibling gate tests stub
it, which is why this state went unnoticed: it is what every first launch of the desktop app looks like).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.skills.gates.oauth_availability import (
    X_LIVE_SEARCH_SKILL_ID,
    X_LIVE_SEARCH_UNAVAILABLE,
    apply_integration_oauth_availability,
)
from app.core.skills.models import Skill
from app.core.storage.types import SkillType
from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import service
from app.services.config.encryption import ConfigEncryptionService

_XAI_PROVIDER = {
    "id": "xai",
    "name": "xai",
    "isEnabled": True,
    "apiUrl": "https://api.x.ai/v1",
    "apiKey": "xai-gate-test-key",
}


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

    encryption = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr("app.database.connection.get_session", get_session)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)
    monkeypatch.setattr("app.services.config.encryption.get_encryption_service", lambda: encryption)
    invalidate_user_configs_cache()
    yield factory
    invalidate_user_configs_cache()
    await engine.dispose()


async def _store_providers(sessions: async_sessionmaker[AsyncSession], value: dict[str, object]) -> None:
    stored, encrypted = service._encrypt_if_sensitive("providers", value)
    async with sessions() as db:
        db.add(
            UserConfig(
                id="id-providers",
                config_key="providers",
                config_value={"_cipher": stored} if encrypted else value,
                is_encrypted=encrypted,
                version="1_0",
                last_device_id="d",
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()


def _x_live_search_skill() -> Skill:
    return Skill(
        id=X_LIVE_SEARCH_SKILL_ID,
        type=SkillType.PREBUILT,
        name="x-live-search",
        description="test",
        storage_path="skills/prebuilt/x-live-search",
        available=True,
    )


async def test_a_fresh_install_lists_x_live_search_as_unavailable(sessions: async_sessionmaker[AsyncSession]) -> None:
    skill = _x_live_search_skill()

    await apply_integration_oauth_availability([skill], AsyncMock())

    assert skill.available is False
    assert skill.unavailable_reason == X_LIVE_SEARCH_UNAVAILABLE


async def test_providers_saved_without_a_default_model_but_with_xai_keep_x_live_search_available(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _store_providers(sessions, {"providers": [_XAI_PROVIDER]})
    skill = _x_live_search_skill()

    await apply_integration_oauth_availability([skill], AsyncMock())

    assert skill.available is True
    assert skill.unavailable_reason is None


async def test_providers_saved_without_a_default_model_and_without_xai_leave_it_unavailable(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _store_providers(sessions, {"providers": [{**_XAI_PROVIDER, "id": "openai", "apiUrl": "https://api.openai.com/v1"}]})
    skill = _x_live_search_skill()

    await apply_integration_oauth_availability([skill], AsyncMock())

    assert skill.available is False
    assert skill.unavailable_reason == X_LIVE_SEARCH_UNAVAILABLE
