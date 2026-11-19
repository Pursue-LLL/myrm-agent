"""The L3 stealth tier connects only through an egress guard that lives exactly as long as the fetch.

Under the strict network policy the browser Scrapling starts could otherwise reach an internal address by a redirect hop,
a subresource or a rebinding name that the URL checks never judged. Scrapling is the only thing replaced here: the guard
is real, so a test can connect to its port while the fetch runs and after it ended. Real Chromium is in
``test_stealth_fetcher_egress_guard_integration``.
"""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.toolkits.browser.pool import EgressGuard, RoundRobinProxyPool
from myrm_agent_harness.toolkits.web_fetch.fetchers.stealth_fetcher import StealthFetcher

pytestmark = pytest.mark.skipif(importlib.util.find_spec("scrapling") is None, reason="scrapling not installed")

_FETCH = "scrapling.fetchers.StealthyFetcher.async_fetch"
_CREATE_GUARD = "myrm_agent_harness.toolkits.browser.pool.egress_guard.create_egress_guard"
_SHIELD = "myrm_agent_harness.toolkits.web_fetch.fetchers.stealth_fetcher.is_ssrf_shield_enabled"
_GUARD_SHIELD = "myrm_agent_harness.toolkits.browser.pool.egress_guard.is_ssrf_shield_enabled"
_PUBLIC_URL = "http://93.184.216.34/"  # a literal: judging it needs no DNS


@pytest.fixture(autouse=True)
def _strict_default_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_ENABLE_SSRF_SHIELD", raising=False)
    for name in ("http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)


def _response(url: str = _PUBLIC_URL) -> MagicMock:
    response = MagicMock()
    response.body = b"<html><body>ok</body></html>"
    response.encoding = "utf-8"
    response.url = url
    response.status = 200
    response.headers = {}
    return response


def _port_of(settings: dict[str, str]) -> int:
    return int(settings["server"].rsplit(":", 1)[1])


async def _accepts(port: int) -> bool:
    try:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except ConnectionRefusedError:
        return False
    writer.close()
    return True


def _browse_call(browse: AsyncMock) -> dict[str, object]:
    browse.assert_awaited_once()
    return browse.await_args.kwargs


class TestStrictPolicy:
    async def test_the_browser_gets_the_guard_for_the_length_of_the_fetch(self) -> None:
        guard = EgressGuard()
        during: dict[str, object] = {}

        async def browse(url: str, **kwargs: object) -> MagicMock:
            settings = kwargs["additional_args"]["proxy"]  # type: ignore[index]
            during["settings"] = settings
            during["listening"] = await _accepts(_port_of(settings))
            return _response(url)

        with patch(_CREATE_GUARD, return_value=guard), patch(_FETCH, new_callable=AsyncMock, side_effect=browse):
            result = await StealthFetcher().fetch(_PUBLIC_URL)

        settings = during["settings"]
        assert result is not None
        assert settings["server"].startswith("socks5://127.0.0.1:")  # type: ignore[index]
        assert settings["bypass"] == "<-loopback>"  # type: ignore[index]
        assert during["listening"] is True
        assert not await _accepts(_port_of(settings))  # type: ignore[arg-type]

    async def test_the_other_options_of_the_fetch_are_unchanged(self) -> None:
        with patch(_FETCH, new_callable=AsyncMock, return_value=_response()) as browse:
            await StealthFetcher().fetch(_PUBLIC_URL)

        options = _browse_call(browse)
        assert options["block_webrtc"] is True  # Scrapling's flags forbid the UDP a guard cannot carry
        assert options["proxy"] is None
        assert options["dns_over_https"] is False
        assert {key: options[key] for key in ("headless", "network_idle", "disable_resources", "solve_cloudflare")} == {
            "headless": True,
            "network_idle": True,
            "disable_resources": True,
            "solve_cloudflare": True,
        }

    @pytest.mark.parametrize("failure", [RuntimeError("browser crashed"), TimeoutError()], ids=["error", "timeout"])
    async def test_the_guard_stops_when_the_browser_fails(self, failure: Exception) -> None:
        guard = EgressGuard()
        ports: list[int] = []

        async def browse(_url: str, **kwargs: object) -> MagicMock:
            ports.append(_port_of(kwargs["additional_args"]["proxy"]))  # type: ignore[index]
            raise failure

        with patch(_CREATE_GUARD, return_value=guard), patch(_FETCH, new_callable=AsyncMock, side_effect=browse):
            result = await StealthFetcher().fetch(_PUBLIC_URL)

        assert result is None
        assert not await _accepts(ports[0])

    async def test_the_guard_stops_when_the_fetch_is_cancelled(self) -> None:
        guard = EgressGuard()
        browsing = asyncio.Event()
        ports: list[int] = []

        async def browse(_url: str, **kwargs: object) -> MagicMock:
            ports.append(_port_of(kwargs["additional_args"]["proxy"]))  # type: ignore[index]
            browsing.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        with patch(_CREATE_GUARD, return_value=guard), patch(_FETCH, new_callable=AsyncMock, side_effect=browse):
            fetch = asyncio.ensure_future(StealthFetcher().fetch(_PUBLIC_URL))
            await asyncio.wait_for(browsing.wait(), 5)
            fetch.cancel()
            with pytest.raises(asyncio.CancelledError):
                await fetch

        assert not await _accepts(ports[0])

    async def test_the_guard_stops_when_the_page_it_ended_on_is_refused(self) -> None:
        guard = EgressGuard()
        ports: list[int] = []

        async def browse(_url: str, **kwargs: object) -> MagicMock:
            ports.append(_port_of(kwargs["additional_args"]["proxy"]))  # type: ignore[index]
            return _response("http://169.254.169.254/latest/meta-data/")

        with (
            patch(_CREATE_GUARD, return_value=guard),
            patch(_FETCH, new_callable=AsyncMock, side_effect=browse),
            pytest.raises(SSRFSecurityError),
        ):
            await StealthFetcher().fetch(_PUBLIC_URL)

        assert not await _accepts(ports[0])

    async def test_a_guard_that_cannot_start_means_no_browser_at_all(self) -> None:
        guard = EgressGuard()

        with (
            patch(_CREATE_GUARD, return_value=guard),
            patch.object(guard, "start", AsyncMock(side_effect=OSError("address in use"))),
            patch(_FETCH, new_callable=AsyncMock) as browse,
        ):
            result = await StealthFetcher().fetch(_PUBLIC_URL)

        assert result is None
        browse.assert_not_awaited()


class TestWhereThereIsNoGuard:
    async def test_the_local_network_policy_leaves_connections_to_the_browser(self) -> None:
        with (
            patch(_CREATE_GUARD) as create_guard,
            patch(_FETCH, new_callable=AsyncMock, return_value=_response()) as browse,
        ):
            await StealthFetcher(allow_private_networks=True).fetch(_PUBLIC_URL)

        create_guard.assert_not_called()
        assert _browse_call(browse)["additional_args"] is None

    async def test_a_proxy_pool_keeps_carrying_the_connections(self) -> None:
        proxies = RoundRobinProxyPool.from_urls(["http://proxy.example:8080"])

        with (
            patch(_CREATE_GUARD) as create_guard,
            patch(_FETCH, new_callable=AsyncMock, return_value=_response()) as browse,
        ):
            await StealthFetcher(proxy_pool=proxies).fetch(_PUBLIC_URL)

        options = _browse_call(browse)
        create_guard.assert_not_called()
        assert options["additional_args"] is None
        assert options["dns_over_https"] is True
        assert str(options["proxy"]).startswith("http://proxy.example:8080")

    async def test_a_disabled_shield_leaves_nothing_to_enforce(self) -> None:
        with (
            patch(_SHIELD, return_value=False),
            patch(_GUARD_SHIELD, return_value=False),
            patch(_FETCH, new_callable=AsyncMock, return_value=_response()) as browse,
        ):
            await StealthFetcher().fetch(_PUBLIC_URL)

        assert _browse_call(browse)["additional_args"] is None

    async def test_an_environment_proxy_owns_the_egress_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp.example:3128")

        with patch(_FETCH, new_callable=AsyncMock, return_value=_response()) as browse:
            await StealthFetcher().fetch(_PUBLIC_URL)

        assert _browse_call(browse)["additional_args"] is None


class TestScraplingContract:
    """The guard reaches Chromium only if Scrapling passes ``additional_args`` to the context unchanged; pin that down."""

    def test_the_proxy_with_its_bypass_reaches_the_context_options(self) -> None:
        from scrapling.engines._browsers._stealth import AsyncStealthySession

        settings = {"server": "socks5://127.0.0.1:1080", "bypass": "<-loopback>"}

        session = AsyncStealthySession(headless=True, block_webrtc=True, additional_args={"proxy": settings})

        assert session._context_options["proxy"] == settings

    def test_scraplings_own_proxy_option_would_drop_the_bypass(self) -> None:
        from scrapling.engines._browsers._stealth import AsyncStealthySession

        session = AsyncStealthySession(headless=True, proxy={"server": "socks5://127.0.0.1:1080"})

        assert "bypass" not in session._context_options["proxy"]

    def test_block_webrtc_forbids_udp_outside_a_proxy(self) -> None:
        from scrapling.engines._browsers._stealth import AsyncStealthySession

        session = AsyncStealthySession(headless=True, block_webrtc=True)

        assert {
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--force-webrtc-ip-handling-policy",
        } <= set(session._browser_options["args"])
