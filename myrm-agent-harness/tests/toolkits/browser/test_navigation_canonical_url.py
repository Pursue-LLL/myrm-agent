"""A browser navigation is judged, granted and loaded under the canonical spelling of its URL.

Chromium folds ``2130706433`` into ``127.0.0.1`` and ``Straße`` into Punycode itself; every check that runs before
the load reads the spelling it was given. ``canonical_navigation_url`` closes that gap at the entries of a browser
request, ``BrowserSession.navigate`` and ``goto_with_ssrf_guard`` (a download by URL does the same, see
``test_download_url_guard``), so the host a check reads is the host Chromium dials.
"""

from __future__ import annotations

from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.core.security.redirect_hop_guard import PrivateOriginGrants
from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import (
    BrowserNavigationBlockedError,
    canonical_navigation_url,
    goto_with_ssrf_guard,
)
from myrm_agent_harness.toolkits.browser.session.browser_session_navigation_mixin import BrowserSessionNavigationMixin
from myrm_agent_harness.utils.errors import ToolError

_GUARD = "myrm_agent_harness.toolkits.browser.navigation.ssrf_guard"


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        ("https://example.com/path", "https://example.com/path"),
        ("HTTP://EXAMPLE.com./a?b=1#c", "http://example.com/a?b=1#c"),
        ("http://2130706433:3000/", "http://127.0.0.1:3000/"),
        ("http://0x7f.1/", "http://127.0.0.1/"),
        ("https://münchen.de:0443/", "https://xn--mnchen-3ya.de:443/"),
        ("https://Straße.example/", "https://xn--strae-oqa.example/"),
        ("http://[0:0:0:0:0:0:0:1]:8080/", "http://[::1]:8080/"),
        ("  https://a.test/ ", "https://a.test/"),
    ],
)
def test_a_network_url_is_loaded_in_the_spelling_chromium_dials(url: str, canonical: str) -> None:
    assert canonical_navigation_url(url) == canonical


@pytest.mark.parametrize(
    "url",
    [
        "about:blank",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hi",
        "ws://example.com/",
        "localhost:3000",
        "example.com/x",
    ],
)
def test_a_url_the_navigator_does_not_load_is_left_to_the_scheme_check(url: str) -> None:
    assert canonical_navigation_url(url) == url


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://good.test\\@evil.test/", "parser-confusing"),
        ("ht\ttp://a.test/", "parser-confusing"),
        ("http://127%2e0%2e0%2e1/", "percent-encoding"),
        ("\x01http://a.test/", "Blocked URL scheme"),
        ("http://a..b/", "Invalid hostname"),
        ("http://a.test:80x/", "Invalid port"),
        ("http://[::1/", "Malformed URL"),
        ("http://[::1]x/", "Malformed URL"),
    ],
)
def test_a_network_url_with_no_canonical_form_is_refused(url: str, reason: str) -> None:
    """``urlparse`` takes ``ht<TAB>tp://`` and ``<C0>http://`` for ``http``, so the scheme check cannot wave them through."""
    with pytest.raises(BrowserNavigationBlockedError, match=reason):
        canonical_navigation_url(url)


def _page(url: str) -> AsyncMock:
    page = AsyncMock()
    request = MagicMock()
    request.url = url
    request.redirected_from = None
    response = MagicMock()
    response.request = request
    page.goto.return_value = response
    page.url = url
    return page


@pytest.mark.asyncio
async def test_the_canonical_url_is_judged_granted_and_loaded() -> None:
    page = _page("http://127.0.0.1:3000/")
    grants = PrivateOriginGrants()

    with (
        patch(f"{_GUARD}.assert_browser_navigation_allowed", new_callable=AsyncMock) as allowed,
        patch(f"{_GUARD}.assert_browser_redirect_chain_allowed", new_callable=AsyncMock),
    ):
        await goto_with_ssrf_guard(page, "http://2130706433:3000/", timeout_ms=1000, grants=grants)

    assert allowed.await_args_list[0].args == ("http://127.0.0.1:3000/", grants)
    assert page.goto.await_args.args == ("http://127.0.0.1:3000/",)
    assert grants.permits("http://127.0.0.1:3000/")


@pytest.mark.asyncio
async def test_a_url_with_no_canonical_form_leaves_the_tab_untouched() -> None:
    page = _page("https://example.com/")

    with pytest.raises(BrowserNavigationBlockedError):
        await goto_with_ssrf_guard(page, "http://good.test\\@evil.test/", timeout_ms=1000)

    page.route.assert_not_awaited()
    page.goto.assert_not_awaited()


def _session(blocked_host: str | None) -> MagicMock:
    session = MagicMock()
    session._ensure_not_user_takeover = AsyncMock()
    session._ensure_components = AsyncMock()
    session._tab_controller.list_tabs.return_value = ["tab"]
    session._hostname_blocked_by_policy = MagicMock(return_value=blocked_host)
    session._assert_not_blocklisted = partial(BrowserSessionNavigationMixin._assert_not_blocklisted, session)
    return session


@pytest.mark.asyncio
async def test_the_session_policy_reads_the_canonical_url() -> None:
    session = _session("blocked.example")

    with pytest.raises(ToolError):
        await BrowserSessionNavigationMixin.navigate(session, "HTTP://2130706433/x")

    session._hostname_blocked_by_policy.assert_called_once_with("http://127.0.0.1/x")


@pytest.mark.asyncio
async def test_the_session_refuses_a_url_with_no_canonical_form_before_touching_any_state() -> None:
    session = _session(None)

    with pytest.raises(BrowserNavigationBlockedError):
        await BrowserSessionNavigationMixin.navigate(session, "http://good.test\\@evil.test/")

    session._ensure_not_user_takeover.assert_not_awaited()
    session._hostname_blocked_by_policy.assert_not_called()
