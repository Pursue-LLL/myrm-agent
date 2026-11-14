"""The in-memory credential store reads its own configs and leaves the process-level config cache as it found it."""

import time

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.channel_bridge import config_cache
from app.core.channel_bridge.config_loader import UserConfigs, load_user_configs
from app.core.types.business import ModelConfig
from app.database.models import ConfigAuditLog, UserConfig
from tests.support.skill_credential_store import CredentialState, bind_credential_readers


def _configs_an_earlier_test_left_cached() -> UserConfigs:
    return UserConfigs(
        model_cfg=ModelConfig(model="earlier-test-model", api_key="earlier-test-key"),
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict=None,
        personal_settings_dict={},
        mcp_dict=None,
    )


@pytest.mark.asyncio
async def test_a_bound_store_reads_its_own_configs_and_gives_the_cache_back_as_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    earlier_entry = (time.monotonic(), _configs_an_earlier_test_left_cached())
    monkeypatch.setitem(config_cache._config_cache, "sandbox", earlier_entry)
    cached_before = dict(config_cache._config_cache)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    try:
        with pytest.MonkeyPatch.context() as patch:
            store = bind_credential_readers(patch, async_sessionmaker(engine, expire_on_commit=False))
            await store.seed(CredentialState(xai_provider="key"))
            configs = await load_user_configs()
            assert configs is not earlier_entry[1]
            assert config_cache._config_cache["sandbox"][1] is configs
        assert config_cache._config_cache == cached_before
        assert config_cache._config_cache["sandbox"] is earlier_entry
    finally:
        await engine.dispose()
