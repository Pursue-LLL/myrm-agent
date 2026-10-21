"""Real-database tests for purging oauthCredentials entries of retired provider issuers.

No mocks on oauth_store: rows are written through ``upsert_oauth_credential`` and
read back through ``decrypt_oauth_credentials`` so the real encrypt/decrypt path
is exercised.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import UserConfig
from app.services.integrations.oauth_store import (
    CONFIG_KEY,
    decrypt_oauth_credentials,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)
from app.services.integrations.retired_provider_oauth_purge import (
    RETIRED_PROVIDER_ISSUERS,
    purge_retired_provider_credentials,
)

_XAI_ENTRY: dict[str, object] = {"token": "xai-token", "refresh_token": "xai-refresh", "expires_at": 1_900_000_000}
_GOOGLE_ENTRY: dict[str, object] = {"token": "google-token", "scope": "drive.readonly"}


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: UserConfig.metadata.create_all(sync_conn, tables=[UserConfig.__table__]))
    async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as session:
        yield session
    await engine.dispose()


async def _stored_credentials(db: AsyncSession) -> dict[str, object]:
    row = await load_oauth_credentials_row(db)
    assert row is not None
    return decrypt_oauth_credentials(row.config_value, row.is_encrypted)


async def _seed(db: AsyncSession, issuers: tuple[str, ...]) -> None:
    for issuer in issuers:
        await upsert_oauth_credential(db, issuer, {"token": f"{issuer}-token", "refresh_token": f"{issuer}-refresh"})


def test_retired_issuers_are_exactly_the_removed_subscription_logins() -> None:
    assert set(RETIRED_PROVIDER_ISSUERS) == {"provider_anthropic", "provider_openai", "provider_copilot"}


async def test_purge_removes_retired_issuers_and_keeps_live_ones(db: AsyncSession) -> None:
    await _seed(db, RETIRED_PROVIDER_ISSUERS)
    await upsert_oauth_credential(db, "xai", _XAI_ENTRY)
    await upsert_oauth_credential(db, "google_workspace", _GOOGLE_ENTRY)

    removed = await purge_retired_provider_credentials(db)

    assert removed == len(RETIRED_PROVIDER_ISSUERS)
    assert await _stored_credentials(db) == {"xai": _XAI_ENTRY, "google_workspace": _GOOGLE_ENTRY}


async def test_purge_removes_a_partial_set(db: AsyncSession) -> None:
    await _seed(db, ("provider_openai",))
    await upsert_oauth_credential(db, "xai", _XAI_ENTRY)

    assert await purge_retired_provider_credentials(db) == 1
    assert await _stored_credentials(db) == {"xai": _XAI_ENTRY}


async def test_purge_is_idempotent(db: AsyncSession) -> None:
    await _seed(db, RETIRED_PROVIDER_ISSUERS)
    await upsert_oauth_credential(db, "xai", _XAI_ENTRY)

    assert await purge_retired_provider_credentials(db) == len(RETIRED_PROVIDER_ISSUERS)
    assert await purge_retired_provider_credentials(db) == 0
    assert await _stored_credentials(db) == {"xai": _XAI_ENTRY}


async def test_purge_without_a_row_creates_nothing(db: AsyncSession) -> None:
    assert await purge_retired_provider_credentials(db) == 0
    assert await load_oauth_credentials_row(db) is None


async def test_purge_does_not_rewrite_a_blob_without_retired_issuers(db: AsyncSession) -> None:
    await upsert_oauth_credential(db, "xai", _XAI_ENTRY)
    row = await load_oauth_credentials_row(db)
    assert row is not None
    stored_before = row.config_value

    assert await purge_retired_provider_credentials(db) == 0

    row_after = await load_oauth_credentials_row(db)
    assert row_after is not None
    # Encryption uses a fresh nonce per write, so an unchanged ciphertext proves no rewrite happened.
    assert row_after.config_value == stored_before


async def test_purge_leaves_an_unparseable_blob_untouched(db: AsyncSession) -> None:
    db.add(
        UserConfig(
            id="row-id",
            config_key=CONFIG_KEY,
            config_value="not-json",
            version="1.0.0",
            last_device_id="sandbox",
            is_encrypted=False,
        )
    )
    await db.commit()

    assert await purge_retired_provider_credentials(db) == 0

    row = await load_oauth_credentials_row(db)
    assert row is not None
    assert row.config_value == "not-json"
