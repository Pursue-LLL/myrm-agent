"""A stored OAuth credential blob sealed under a key this device no longer has makes the refresh unavailable, not an error.

[INPUT]
app.services.agent.oauth_refresher::refresh_oauth_token
app.services.integrations.oauth_store::encrypt_oauth_credentials

[OUTPUT]
That the refresh returns ``None`` (the same answer as "no credentials stored") when the blob cannot be decrypted, so the
callers that treat ``None`` as "token unavailable" (wiki source sync) report that instead of crashing with a crypto error.

[POS]
Real ORM table on an in-memory database; the encryption service is a different local key than the one that sealed the row.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import UserConfig
from app.services.agent import oauth_refresher
from app.services.config.encryption import ConfigEncryptionService
from app.services.integrations.oauth_store import encrypt_oauth_credentials

_ISSUER = "google_workspace"


def _local_encryption() -> ConfigEncryptionService:
    return ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)


@pytest.fixture
async def sessions() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_credentials_sealed_under_a_lost_key_are_reported_unavailable(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    sealed, encrypted = encrypt_oauth_credentials(
        {_ISSUER: {"token": "t", "refresh_token": "r", "token_url": "https://oauth.example/token", "expires_at": 0}},
        service=_local_encryption(),
    )
    assert encrypted
    async with sessions() as db:
        db.add(
            UserConfig(
                id="id-oauth",
                config_key="oauthCredentials",
                config_value=sealed if isinstance(sealed, dict) else {"_cipher": sealed},
                is_encrypted=True,
                version="1_0",
                last_device_id="d",
            )
        )
        await db.commit()

    @asynccontextmanager
    async def get_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    current = _local_encryption()
    monkeypatch.setattr(oauth_refresher, "get_session", get_session)
    monkeypatch.setattr(oauth_refresher, "get_encryption_service", lambda: current)
    monkeypatch.setattr("app.services.integrations.oauth_store.get_encryption_service", lambda: current)

    assert await oauth_refresher.refresh_oauth_token(_ISSUER) is None
