"""SaaS platform provider seed 集成测试：真实 ConfigService + 内存 SQLite。

关键路径（ConfigService 真实读写 + providers 配置加密落库 + 读取解密）不 mock，
仅将 session factory 指向测试内存库以隔离数据。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete

from app.config.deploy_mode import get_deploy_mode
from app.core.channel_bridge.config_cache import _config_cache, _get_cached
from app.database.models import UserConfig
from app.platform_utils.sandbox.saas_providers_seed import (
    _PLATFORM_PROVIDER_ID,
    seed_saas_platform_providers_if_needed,
)
from app.services.config.service import ConfigService

_LITE_MODEL = "openrouter/anthropic/claude-sonnet-4"
_INGRESS = "https://example.test"


@pytest.fixture
async def sandbox_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """sandbox env + 共享测试 DB 的 providers 行清理；退出时还原。"""
    from app.database.connection import get_session_factory

    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    monkeypatch.setenv("MYRM_SAAS_DEFAULT_LITE_MODEL", _LITE_MODEL)
    monkeypatch.setenv("CP_PUBLIC_INGRESS_URL", _INGRESS)
    get_deploy_mode.cache_clear()

    async def _clear_providers() -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(
                delete(UserConfig).where(UserConfig.config_key == "providers")
            )
            await session.commit()

    await _clear_providers()
    _config_cache.clear()
    yield
    get_deploy_mode.cache_clear()
    await _clear_providers()
    _config_cache.clear()


class TestSeedIntegration:
    async def test_seed_persists_platform_provider_via_real_db(self, sandbox_db: None) -> None:
        """全新沙箱：真实 ConfigService 将 platform provider 加密落库并可读回。"""
        await seed_saas_platform_providers_if_needed()

        record = await ConfigService().get("providers")
        assert record is not None
        value = record.value
        assert isinstance(value, dict)
        providers = value["providers"]
        assert isinstance(providers, list) and len(providers) == 1
        assert providers[0]["id"] == _PLATFORM_PROVIDER_ID
        default_cfg = value["defaultModelConfig"]
        assert isinstance(default_cfg, dict)
        primary = default_cfg["baseModel"]["primary"]
        assert primary == {"providerId": _PLATFORM_PROVIDER_ID, "model": "anthropic/claude-sonnet-4"}

    async def test_seed_skips_when_user_providers_already_configured(
        self, sandbox_db: None
    ) -> None:
        """已有用户 provider：seed 不覆盖真实已落库的配置。"""
        service = ConfigService()
        user_value: dict[str, object] = {
            "providers": [
                {"id": "anthropic", "providerType": "anthropic", "isEnabled": True}
            ],
            "defaultModelConfig": {
                "baseModel": {
                    "primary": {"providerId": "anthropic", "model": "claude-opus"}
                }
            },
        }
        await service.set("providers", user_value, "test-device")

        await seed_saas_platform_providers_if_needed()

        record = await service.get("providers")
        assert record is not None
        value = record.value
        assert isinstance(value, dict)
        providers = value["providers"]
        assert isinstance(providers, list) and len(providers) == 1
        assert providers[0]["id"] == "anthropic"

    async def test_seed_invalidates_config_cache(self, sandbox_db: None) -> None:
        """seed 写入后 config cache 必须失效，否则 channel_bridge 读到旧空配置。"""
        # 模拟 seed 前已产生的旧缓存（TTL 未过期）；占位对象仅用于验证失效
        _config_cache["sandbox"] = (time.monotonic(), object())  # type: ignore[assignment]
        assert _get_cached("sandbox") is not None

        await seed_saas_platform_providers_if_needed()

        assert _get_cached("sandbox") is None
