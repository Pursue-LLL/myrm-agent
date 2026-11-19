"""How the egress guard is wired into the pool: which contexts connect through it, and what else changes with it.

The guard itself is covered by ``test_egress_guard``; here a fake guard shows what the context factory and the pool
ask of it, and the browsers are doubles. Real Chromium is in ``test_egress_guard_integration``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser import enhancers
from myrm_agent_harness.toolkits.browser.pool import (
    BrowserInstance,
    BrowserPoolConfig,
    ContextType,
    EgressGuard,
    EgressGuardError,
    GlobalBrowserPool,
    RoundRobinProxyPool,
)
from myrm_agent_harness.toolkits.browser.pool.browser_pool import _DEFAULT_LAUNCH_OPTIONS
from myrm_agent_harness.toolkits.browser.pool.config import BrowserEngine
from myrm_agent_harness.toolkits.browser.pool.context_factory import ContextFactory

_WEBRTC_FLAG = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
_DOH_FLAG = "--dns-over-https-templates=https://cloudflare-dns.com/dns-query"
_GUARD_PROXY = {"server": "socks5://127.0.0.1:1080", "bypass": "<-loopback>"}


def _fake_guard() -> MagicMock:
    guard = MagicMock(spec=EgressGuard)
    guard.verify_routing = AsyncMock()
    guard.start = AsyncMock(return_value=_GUARD_PROXY)
    guard.stop = AsyncMock()
    return guard


def _browser() -> MagicMock:
    context = MagicMock()
    context.add_init_script = AsyncMock()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    return browser


@pytest.fixture(autouse=True)
def _no_page_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enhancers, "install_document_script_injection", AsyncMock())


def _proxy_option(browser: MagicMock) -> object:
    return browser.new_context.await_args.kwargs.get("proxy")


class TestContextsOfLaunchedBrowsers:
    async def test_a_context_connects_through_the_guard_once_the_browser_proved_it_honors_it(self) -> None:
        guard, browser = _fake_guard(), _browser()
        steps = MagicMock()
        steps.attach_mock(guard.verify_routing, "verify")
        steps.attach_mock(guard.start, "start")
        steps.attach_mock(browser.new_context, "new_context")

        await ContextFactory(egress_guard=guard).create_context(browser, ContextType.AGENT.value, guard_egress=True)

        assert _proxy_option(browser) == _GUARD_PROXY
        assert [call[0] for call in steps.mock_calls] == ["verify", "start", "new_context"]
        guard.verify_routing.assert_awaited_once_with(browser)

    async def test_a_browser_that_does_not_route_through_the_guard_gets_no_context_at_all(self) -> None:
        guard, browser = _fake_guard(), _browser()
        guard.verify_routing.side_effect = EgressGuardError("not routed")

        with pytest.raises(EgressGuardError, match="not routed"):
            await ContextFactory(egress_guard=guard).create_context(browser, ContextType.AGENT.value, guard_egress=True)

        browser.new_context.assert_not_awaited()

    @pytest.mark.parametrize(
        ("factory_has_guard", "options"),
        [
            pytest.param(False, {"guard_egress": True}, id="no-guard-in-the-factory"),
            pytest.param(True, {"guard_egress": False}, id="browser-not-launched-by-the-pool"),
            pytest.param(True, {"guard_egress": True, "extension_attached": True}, id="the-users-own-browser"),
        ],
    )
    async def test_every_other_context_keeps_its_own_network(
        self, factory_has_guard: bool, options: dict[str, bool]
    ) -> None:
        guard, browser = _fake_guard(), _browser()

        await ContextFactory(egress_guard=guard if factory_has_guard else None).create_context(
            browser, ContextType.AGENT.value, **options
        )

        assert _proxy_option(browser) is None
        guard.verify_routing.assert_not_awaited()
        guard.start.assert_not_awaited()

    async def test_a_proxy_the_context_asks_for_is_kept(self) -> None:
        guard, browser = _fake_guard(), _browser()
        explicit = {"server": "http://proxy.example:3128"}

        await ContextFactory(egress_guard=guard).create_context(
            browser, ContextType.AGENT.value, extra_kwargs={"proxy": explicit}, guard_egress=True
        )

        assert _proxy_option(browser) == explicit
        guard.verify_routing.assert_not_awaited()

    async def test_a_proxy_of_the_pool_is_kept(self) -> None:
        guard, browser = _fake_guard(), _browser()
        proxies = RoundRobinProxyPool.from_urls(["http://127.0.0.1:8080"])

        await ContextFactory(proxy_pool=proxies, egress_guard=guard).create_context(
            browser, ContextType.AGENT.value, guard_egress=True
        )

        assert _proxy_option(browser) is not None
        assert _proxy_option(browser) != _GUARD_PROXY
        guard.start.assert_not_awaited()

    async def test_a_context_whose_policy_allows_private_networks_is_not_held_to_the_strict_one(self) -> None:
        guard, browser = _fake_guard(), _browser()

        await ContextFactory(egress_guard=guard).create_context(
            browser, ContextType.AGENT.value, extra_kwargs={"allow_private_networks": True}, guard_egress=True
        )

        assert _proxy_option(browser) is None
        guard.start.assert_not_awaited()


class TestPoolLaunchFlags:
    @staticmethod
    def _args(pool: GlobalBrowserPool) -> list[str]:
        args = pool._launch_options["args"]
        assert isinstance(args, list)
        return args

    def test_a_pool_with_a_guard_forbids_udp_outside_a_proxy(self) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal(), egress_guard=_fake_guard())

        assert self._args(pool).count(_WEBRTC_FLAG) == 1

    def test_a_pool_without_a_guard_leaves_webrtc_alone(self) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal())

        assert _WEBRTC_FLAG not in self._args(pool)

    def test_the_flag_comes_with_the_dns_over_https_flag_of_a_proxy_pool(self) -> None:
        pool = GlobalBrowserPool(
            max_browsers=1,
            config=BrowserPoolConfig.minimal(),
            proxy_pool=RoundRobinProxyPool.from_urls(["http://127.0.0.1:8080"]),
            egress_guard=_fake_guard(),
        )

        assert {_WEBRTC_FLAG, _DOH_FLAG} <= set(self._args(pool))

    def test_the_options_of_the_caller_and_the_defaults_are_not_changed(self) -> None:
        mine: dict[str, object] = {"headless": True, "args": ["--mute-audio"]}
        defaults_before = list(_DEFAULT_LAUNCH_OPTIONS["args"])  # type: ignore[call-overload]

        pool = GlobalBrowserPool(
            max_browsers=1, config=BrowserPoolConfig.minimal(), launch_options=mine, egress_guard=_fake_guard()
        )

        assert mine == {"headless": True, "args": ["--mute-audio"]}
        assert _DEFAULT_LAUNCH_OPTIONS["args"] == defaults_before
        assert "--mute-audio" in self._args(pool)

    async def test_the_flag_stays_while_the_proxy_pool_is_reloaded(self) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal(), egress_guard=_fake_guard())

        await pool.update_proxy_pool(RoundRobinProxyPool.from_urls(["http://127.0.0.1:8080"]))
        assert {_WEBRTC_FLAG, _DOH_FLAG} <= set(self._args(pool))

        await pool.update_proxy_pool(None)
        assert _WEBRTC_FLAG in self._args(pool)
        assert _DOH_FLAG not in self._args(pool)

    async def test_the_context_factory_keeps_the_guard_when_the_proxy_pool_is_reloaded(self) -> None:
        guard = _fake_guard()
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal(), egress_guard=guard)

        await pool.update_proxy_pool(None)

        assert pool._context_factory._egress_guard is guard


class TestWhichBrowsersAreGuarded:
    @staticmethod
    def _instance(*, managed: bool, engine: BrowserEngine) -> BrowserInstance:
        return BrowserInstance(browser=MagicMock(), engine=engine.value, is_managed=managed)

    @pytest.mark.parametrize(
        ("has_guard", "managed", "engine", "expected"),
        [
            pytest.param(True, True, BrowserEngine.CHROMIUM_PATCHRIGHT, True, id="launched-chromium"),
            pytest.param(False, True, BrowserEngine.CHROMIUM_PATCHRIGHT, False, id="no-guard"),
            pytest.param(True, False, BrowserEngine.CHROMIUM_PATCHRIGHT, False, id="attached-cdp-remote-or-extension"),
            pytest.param(True, True, BrowserEngine.FIREFOX_CAMOUFOX, False, id="camoufox"),
        ],
    )
    def test_only_a_chromium_the_pool_launched_is_pointed_at_the_guard(
        self, has_guard: bool, managed: bool, engine: BrowserEngine, expected: bool
    ) -> None:
        pool = GlobalBrowserPool(
            max_browsers=1, config=BrowserPoolConfig.minimal(), egress_guard=_fake_guard() if has_guard else None
        )

        assert pool._guards_egress(self._instance(managed=managed, engine=engine)) is expected


class TestPoolShutdown:
    async def test_the_guard_stops_after_the_browsers_whose_connections_it_carried(self) -> None:
        guard = _fake_guard()
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal(), egress_guard=guard)
        instance = BrowserInstance(browser=MagicMock(), is_managed=True)
        instance.browser.close = AsyncMock()
        pool._browsers.append(instance)
        steps = MagicMock()
        steps.attach_mock(instance.browser.close, "close_browser")
        steps.attach_mock(guard.stop, "stop_guard")

        await pool.shutdown()

        assert [call[0] for call in steps.mock_calls] == ["close_browser", "stop_guard"]

    async def test_a_pool_without_a_guard_shuts_down_as_before(self) -> None:
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal())

        await pool.shutdown()

    async def test_a_stopped_guard_leaves_a_new_context_with_a_readable_error(self) -> None:
        guard = EgressGuard()
        await guard.stop()

        with pytest.raises(EgressGuardError, match="stopped"):
            await ContextFactory(egress_guard=guard).create_context(
                _browser(), ContextType.AGENT.value, guard_egress=True
            )
