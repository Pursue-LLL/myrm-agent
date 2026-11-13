"""The in-memory credential store leaves nothing of what it stored in the caches the next test reads."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.channel_bridge import config_cache
from app.core.channel_bridge.config_loader import load_user_configs
from app.database.models import ConfigAuditLog, UserConfig
from tests.support.skill_credential_store import CredentialState, bind_credential_readers


@pytest.mark.asyncio
async def test_the_configs_read_from_a_bound_store_are_cached_only_until_the_test_that_bound_it_ends() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    cached_before = dict(config_cache._config_cache)
    try:
        with pytest.MonkeyPatch.context() as patch:
            store = bind_credential_readers(patch, async_sessionmaker(engine, expire_on_commit=False))
            await store.seed(CredentialState(xai_provider="key"))
            await load_user_configs()
            assert "sandbox" in config_cache._config_cache
        assert config_cache._config_cache == cached_before
    finally:
        await engine.dispose()
