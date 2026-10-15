"""Unit tests: a session's ``allow_private_networks`` reaches the context-level request filter.

The pool installs a request filter on every context (default resource blocking), and that filter
revalidates each hop against private/metadata ranges. Without the flag, local mode would still
have loopback requests aborted even though the navigator already allows them.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist, install_domain_filter
from myrm_agent_harness.toolkits.browser.pool.browser_pool import ContextType
from myrm_agent_harness.toolkits.browser.pool.config import ResourceBlockConfig
from myrm_agent_harness.toolkits.browser.pool.context_factory import ContextFactory
from myrm_agent_harness.toolkits.browser.session import BrowserSession

_LOOPBACK_URL = "http://127.0.0.1:8080/app.js"
_AD_URL = "https://ad.doubleclick.net/tracking.js"


def _route_for(url: str, resource_type: str = "fetch") -> AsyncMock:
    route = AsyncMock()
    route.request = MagicMock()
    route.request.url = url
    route.request.resource_type = resource_type
    return route


async def _installed_handler(*, allow_private_networks: bool) -> object:
    context = AsyncMock()
    context.route = AsyncMock()
    context.on = MagicMock()
    await install_domain_filter(
        context,
        DomainAllowlist(patterns=()),
        resource_block=ResourceBlockConfig(block_ad_domains=True),
        allow_private_networks=allow_private_networks,
    )
    return context.route.call_args[0][1]


class TestRequestFilterPrivateNetworks:
    @pytest.mark.asyncio
    async def test_loopback_is_aborted_by_default(self) -> None:
        handler = await _installed_handler(allow_private_networks=False)
        route = _route_for(_LOOPBACK_URL)

        await handler(route)  # type: ignore[operator]

        route.abort.assert_called_once_with("blockedbyclient")
        route.fallback.assert_not_called()

    @pytest.mark.asyncio
    async def test_loopback_passes_in_local_mode(self) -> None:
        handler = await _installed_handler(allow_private_networks=True)
        route = _route_for(_LOOPBACK_URL)

        await handler(route)  # type: ignore[operator]

        route.fallback.assert_called_once()
        route.abort.assert_not_called()

    @pytest.mark.asyncio
    async def test_ad_domains_stay_blocked_in_local_mode(self) -> None:
        handler = await _installed_handler(allow_private_networks=True)
        route = _route_for(_AD_URL, resource_type="script")

        await handler(route)  # type: ignore[operator]

        route.abort.assert_called_once_with("blockedbyclient")


def _browser_and_context() -> tuple[MagicMock, AsyncMock]:
    context = AsyncMock()
    context.set_default_timeout = MagicMock()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    return browser, context


class TestContextFactoryForwarding:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("extra_key", ["domain_allowlist", "resource_block"])
    async def test_flag_reaches_installer_and_not_new_context(self, extra_key: str) -> None:
        browser, _ = _browser_and_context()
        extra_value = (
            DomainAllowlist.from_strings(["example.com"])
            if extra_key == "domain_allowlist"
            else ResourceBlockConfig(block_ad_domains=True)
        )
        install = AsyncMock()

        with patch("myrm_agent_harness.toolkits.browser.domain_filter.install_domain_filter", new=install):
            await ContextFactory().create_context(
                browser,
                ContextType.CRAWL.value,
                extra_kwargs={extra_key: extra_value, "allow_private_networks": True},
            )

        assert install.await_args is not None
        assert install.await_args.kwargs["allow_private_networks"] is True
        assert "allow_private_networks" not in browser.new_context.call_args.kwargs

    @pytest.mark.asyncio
    async def test_flag_defaults_to_false(self) -> None:
        browser, _ = _browser_and_context()
        install = AsyncMock()

        with patch("myrm_agent_harness.toolkits.browser.domain_filter.install_domain_filter", new=install):
            await ContextFactory().create_context(
                browser,
                ContextType.CRAWL.value,
                extra_kwargs={"resource_block": ResourceBlockConfig(block_ad_domains=True)},
            )

        assert install.await_args is not None
        assert install.await_args.kwargs["allow_private_networks"] is False


class TestSessionContextKwargs:
    def test_local_mode_session_publishes_flag(self) -> None:
        session = BrowserSession(MagicMock(), ContextType.AGENT, allow_private_networks=True)

        assert session._tab_controller._context_kwargs == {"allow_private_networks": True}

    def test_default_session_publishes_nothing(self) -> None:
        session = BrowserSession(MagicMock(), ContextType.AGENT)

        assert session._tab_controller._context_kwargs is None
