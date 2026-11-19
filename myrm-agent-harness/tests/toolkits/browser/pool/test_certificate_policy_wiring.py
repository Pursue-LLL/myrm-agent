"""How the operator's certificate choice travels from ``BrowserConfig`` into the contexts the pool creates.

The options the factory builds are covered by ``test_context_factory``; here the pool builds its factory from the
config, at start and again whenever the pool replaces it. Real Chromium is in
``test_certificate_verification_integration``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, GlobalBrowserPool, RoundRobinProxyPool
from myrm_agent_harness.toolkits.browser.pool.config import BrowserMode

_PRESETS: list[Callable[[], BrowserPoolConfig]] = [
    BrowserPoolConfig.minimal,
    BrowserPoolConfig.standard,
    BrowserPoolConfig.defensive,
]


def _config(*, ignore_https_errors: bool) -> BrowserPoolConfig:
    return dataclasses.replace(BrowserPoolConfig.minimal(), ignore_https_errors=ignore_https_errors)


class TestConfig:
    @pytest.mark.parametrize("preset", _PRESETS, ids=lambda preset: preset.__name__)
    def test_every_preset_verifies_certificates(self, preset: Callable[[], BrowserPoolConfig]) -> None:
        assert preset().ignore_https_errors is False

    def test_a_config_built_without_arguments_verifies_certificates(self) -> None:
        assert BrowserPoolConfig().ignore_https_errors is False

    @pytest.mark.parametrize("mode", list(BrowserMode))
    def test_the_choice_survives_a_mode_switch(self, mode: BrowserMode) -> None:
        assert _config(ignore_https_errors=True).with_mode(mode).ignore_https_errors is True


class TestPool:
    @pytest.mark.parametrize("opted_out", [False, True])
    def test_the_pool_builds_its_factory_from_the_config(self, opted_out: bool) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=_config(ignore_https_errors=opted_out))

        assert pool._context_factory._ignore_https_errors is opted_out

    def test_a_pool_without_a_config_verifies_certificates(self) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=None)

        assert pool._context_factory._ignore_https_errors is False

    @pytest.mark.parametrize("opted_out", [False, True])
    async def test_the_choice_survives_a_proxy_pool_reload(self, opted_out: bool) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=_config(ignore_https_errors=opted_out))

        await pool.update_proxy_pool(RoundRobinProxyPool.from_urls(["http://127.0.0.1:8080"]))
        assert pool._context_factory._ignore_https_errors is opted_out

        await pool.update_proxy_pool(None)
        assert pool._context_factory._ignore_https_errors is opted_out

    @pytest.mark.parametrize("opted_out", [False, True])
    async def test_the_choice_survives_a_remote_endpoint_reload(self, opted_out: bool) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=_config(ignore_https_errors=opted_out))

        await pool.update_remote_endpoint("wss://browser.example/", None)
        await pool.update_proxy_pool(None)

        assert pool.config.ignore_https_errors is opted_out
        assert pool._context_factory._ignore_https_errors is opted_out
