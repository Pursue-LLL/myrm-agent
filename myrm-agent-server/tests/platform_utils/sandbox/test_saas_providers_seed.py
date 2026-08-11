"""SaaS platform provider seed 逻辑单元测试。

覆盖场景:
- 全新沙箱（无 providers 配置）首次启动 seed 平台 lite provider + 默认模型
- 已有 provider 且已设默认模型 -> 跳过（不覆盖用户配置）
- 已有 provider 但未设默认模型 -> 跳过（回归保护：seed 条件与意图一致）
- providers 为空数组 -> 按全新沙箱处理，重新 seed
- 非 sandbox 部署模式 / 缺少环境变量 -> 直接返回，不触碰配置
- _parse_lite_model_ref 解析规则
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config.deploy_mode import get_deploy_mode
from app.platform_utils.sandbox.saas_providers_seed import (
    _PLATFORM_PROVIDER_ID,
    _parse_lite_model_ref,
    seed_saas_platform_providers_if_needed,
)

_LITE_MODEL = "openrouter/anthropic/claude-sonnet-4"
_INGRESS = "https://example.test"


class _FakeConfigService:
    """ConfigService 替身：记录 get 返回值与 set 调用，避免引入数据库/加密依赖。"""

    def __init__(self, record: object | None) -> None:
        self._record = record
        self.set_calls: list[tuple[str, object, str, object | None]] = []

    async def get(self, config_key: str) -> object | None:
        return self._record

    async def set(
        self,
        config_key: str,
        value: dict[str, object],
        device_id: str,
        expected_version: str | None = None,
    ) -> object:
        self.set_calls.append((config_key, value, device_id, expected_version))
        return None


def _record(value: dict[str, object], version: str = "1_0") -> SimpleNamespace:
    return SimpleNamespace(value=value, version=version)


def _patch_service(monkeypatch: pytest.MonkeyPatch, fake: _FakeConfigService) -> None:
    monkeypatch.setattr(
        "app.services.config.service.ConfigService",
        lambda: fake,
    )


@pytest.fixture
def sandbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """进入 sandbox 模式并注入 seed 所需环境变量，退出时恢复缓存。"""
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    monkeypatch.setenv("MYRM_SAAS_DEFAULT_LITE_MODEL", _LITE_MODEL)
    monkeypatch.setenv("CP_PUBLIC_INGRESS_URL", _INGRESS)
    get_deploy_mode.cache_clear()
    yield
    get_deploy_mode.cache_clear()


class TestParseLiteModelRef:
    def test_valid_ref(self) -> None:
        assert _parse_lite_model_ref("openrouter/anthropic/claude-sonnet-4") == (
            "openrouter",
            "anthropic/claude-sonnet-4",
        )

    def test_non_openrouter_prefix_rejected(self) -> None:
        assert _parse_lite_model_ref("anthropic/claude-sonnet-4") is None

    def test_wrong_part_count_rejected(self) -> None:
        assert _parse_lite_model_ref("openrouter/anthropic") is None

    def test_whitespace_stripped(self) -> None:
        assert _parse_lite_model_ref("  openrouter/gpt-4o/mini  ") == (
            "openrouter",
            "gpt-4o/mini",
        )


class TestSeedFreshSandbox:
    async def test_seeds_platform_provider_when_no_record(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeConfigService(record=None)
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert len(fake.set_calls) == 1
        key, value, device_id, _expected_version = fake.set_calls[0]
        assert key == "providers"
        assert device_id == "saas-platform-seed"
        providers = value["providers"]
        assert isinstance(providers, list)
        assert providers[0]["id"] == _PLATFORM_PROVIDER_ID
        assert providers[0]["isEnabled"] is True
        default_cfg = value["defaultModelConfig"]
        assert default_cfg["baseModel"]["primary"] == {
            "providerId": _PLATFORM_PROVIDER_ID,
            "model": "anthropic/claude-sonnet-4",
        }

    async def test_seeds_when_providers_is_empty_list(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeConfigService(record=_record({"providers": []}))
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert len(fake.set_calls) == 1


class TestSeedSkipsExistingConfiguration:
    async def test_skips_when_provider_and_default_model_exist(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_provider = {"id": "anthropic", "providerType": "anthropic"}
        existing = {
            "providers": [user_provider],
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "anthropic", "model": "claude-opus"}}
            },
        }
        fake = _FakeConfigService(record=_record(existing))
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []

    async def test_skips_when_provider_exists_but_no_default_model(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """回归保护：用户已配 provider 但未设默认模型时，seed 不得覆盖其配置。"""
        user_provider = {"id": "anthropic", "providerType": "anthropic"}
        existing = {"providers": [user_provider], "defaultModelConfig": {}}
        fake = _FakeConfigService(record=_record(existing))
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []

    async def test_skips_when_default_model_set_but_providers_missing(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        existing = {
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "anthropic", "model": "claude-opus"}}
            }
        }
        fake = _FakeConfigService(record=_record(existing))
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []


class TestSeedGuardClauses:
    async def test_returns_early_outside_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEPLOY_MODE", "local")
        get_deploy_mode.cache_clear()
        monkeypatch.setenv("MYRM_SAAS_DEFAULT_LITE_MODEL", _LITE_MODEL)
        monkeypatch.setenv("CP_PUBLIC_INGRESS_URL", _INGRESS)
        fake = _FakeConfigService(record=None)
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []
        get_deploy_mode.cache_clear()

    async def test_returns_early_without_lite_model_env(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MYRM_SAAS_DEFAULT_LITE_MODEL", raising=False)
        fake = _FakeConfigService(record=None)
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []

    async def test_returns_early_without_ingress_env(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CP_PUBLIC_INGRESS_URL", raising=False)
        fake = _FakeConfigService(record=None)
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []

    async def test_returns_early_on_invalid_lite_model_ref(
        self, sandbox_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MYRM_SAAS_DEFAULT_LITE_MODEL", "anthropic/claude-sonnet-4")
        fake = _FakeConfigService(record=None)
        _patch_service(monkeypatch, fake)

        await seed_saas_platform_providers_if_needed()

        assert fake.set_calls == []
