"""A download by URL is judged like a navigation to the same URL, at both ends of the request.

``BrowserSession.download_url`` canonicalizes the URL, applies the URL blocklist and the SSRF policy before the browser is
asked, and judges the address the download finally came from. A request that ends on a page instead of a file leaves
the tab on that page, so the page is judged too and a refused one is discarded. The session flow and the Navigator
policy are pinned with scripted doubles here; ``test_download_url_integration`` runs them against real Chromium.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.core.security.redirect_hop_guard import PrivateOriginGrants
from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist
from myrm_agent_harness.toolkits.browser.domain_filter.context_lists import DomainListPolicy, bind_domain_lists
from myrm_agent_harness.toolkits.browser.navigation import Navigator
from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session.browser_session_download_mixin import BrowserSessionDownloadMixin
from myrm_agent_harness.toolkits.browser.session.browser_session_navigation_mixin import BrowserSessionNavigationMixin
from myrm_agent_harness.toolkits.browser.session.download_manager import DownloadResult
from myrm_agent_harness.toolkits.browser.utils.private_origins import private_origin_grants
from myrm_agent_harness.utils.errors import ToolError

_PIN = "myrm_agent_harness.core.security.guards.ssrf.async_pin_url"
_TAB_URL = "https://start.example/page"
_SAVED = DownloadResult(url="https://cdn.example/a.pdf", path="/tmp/a.pdf", file_name="a.pdf", file_size=3)


@dataclass
class _Rig:
    """A session whose collaborators are doubles, plus what the flow did to them, in order."""

    session: MagicMock
    page: MagicMock
    navigator: MagicMock
    order: list[str] = field(default_factory=list)

    @property
    def request(self) -> AsyncMock:
        manager_request: AsyncMock = self.session._download_manager.download_url
        return manager_request


def _rig(
    *, blocked_host: str | None = None, result: DownloadResult | None = _SAVED, lands_on: str | None = None
) -> _Rig:
    """``lands_on`` is where the tab ends up when the request produces no download."""
    session = MagicMock()
    page = MagicMock()
    page.url = _TAB_URL
    navigator = MagicMock()
    rig = _Rig(session=session, page=page, navigator=navigator)

    async def admit(_url: str) -> None:
        rig.order.append("admit")

    async def request(*_args: object, **_kwargs: object) -> DownloadResult | None:
        rig.order.append("request")
        if lands_on is not None:
            page.url = lands_on
        return result

    session._ensure_components = AsyncMock()
    session._hostname_blocked_by_policy = MagicMock(return_value=blocked_host)
    session._assert_not_blocklisted = partial(BrowserSessionNavigationMixin._assert_not_blocklisted, session)
    session._tab_controller.get_active_page.return_value = page
    session._download_manager.download_url = AsyncMock(side_effect=request)
    session._require_navigator.return_value = navigator
    navigator.admit_download = AsyncMock(side_effect=admit)
    navigator.assert_landed_allowed = AsyncMock()
    return rig


async def _download(rig: _Rig, url: str = "https://public.example/a.pdf") -> DownloadResult | None:
    return await BrowserSessionDownloadMixin.download_url(rig.session, url)


class TestSessionFlow:
    @pytest.mark.asyncio
    async def test_the_browser_is_asked_for_the_canonical_url_after_it_is_admitted(self) -> None:
        rig = _rig()

        await BrowserSessionDownloadMixin.download_url(rig.session, "HTTP://2130706433:8080/a.pdf", 7.0)

        rig.navigator.admit_download.assert_awaited_once_with("http://127.0.0.1:8080/a.pdf")
        rig.request.assert_awaited_once_with(rig.page, "http://127.0.0.1:8080/a.pdf", 7.0)
        assert rig.order == ["admit", "request"]

    @pytest.mark.asyncio
    async def test_a_url_with_no_canonical_form_never_reaches_the_browser(self) -> None:
        rig = _rig()

        with pytest.raises(BrowserNavigationBlockedError):
            await _download(rig, "http://good.test\\@evil.test/a.pdf")

        rig.session._ensure_components.assert_not_awaited()
        rig.navigator.admit_download.assert_not_awaited()
        rig.request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_blocklist_reads_the_canonical_host_and_stops_the_request(self) -> None:
        rig = _rig(blocked_host="blocked.example")

        with pytest.raises(ToolError) as refusal:
            await _download(rig, "HTTP://2130706433/x")

        assert refusal.value.error_code == "BROWSER_URL_BLOCKLIST"
        rig.session._hostname_blocked_by_policy.assert_called_once_with("http://127.0.0.1/x")
        rig.navigator.admit_download.assert_not_awaited()
        rig.request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_refused_admission_stops_the_request(self) -> None:
        rig = _rig()
        rig.navigator.admit_download.side_effect = BrowserNavigationBlockedError("SSRF blocked: metadata endpoint")

        with pytest.raises(BrowserNavigationBlockedError, match="metadata"):
            await _download(rig)

        rig.request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_saved_download_is_returned_without_judging_the_tab(self) -> None:
        rig = _rig(result=_SAVED)

        assert await _download(rig) is _SAVED

        rig.navigator.assert_landed_allowed.assert_not_awaited()


class TestRequestThatEndedOnAPage:
    @pytest.mark.asyncio
    async def test_the_page_the_tab_landed_on_is_judged_and_a_refused_one_discarded(self) -> None:
        rig = _rig(result=None, lands_on="http://127.0.0.1:9/internal")
        rig.navigator.assert_landed_allowed.side_effect = BrowserNavigationBlockedError("SSRF blocked: loopback")

        with pytest.raises(BrowserNavigationBlockedError, match="loopback"):
            await _download(rig)

        rig.navigator.assert_landed_allowed.assert_awaited_once_with(
            "http://127.0.0.1:9/internal", discard_document=True
        )

    @pytest.mark.asyncio
    async def test_an_allowed_landing_page_is_left_alone(self) -> None:
        rig = _rig(result=None, lands_on="https://public.example/login")

        assert await _download(rig) is None

        rig.navigator.assert_landed_allowed.assert_awaited_once_with(
            "https://public.example/login", discard_document=True
        )

    @pytest.mark.parametrize("lands_on", [None, _TAB_URL, "about:blank", "chrome-error://chromewebdata/"])
    @pytest.mark.asyncio
    async def test_a_tab_that_did_not_move_to_a_network_page_is_not_judged(self, lands_on: str | None) -> None:
        rig = _rig(result=None, lands_on=lands_on)

        assert await _download(rig) is None

        rig.navigator.assert_landed_allowed.assert_not_awaited()


def _navigator(page: MagicMock, *, local: bool = False, grants: PrivateOriginGrants | None = None) -> Navigator:
    return Navigator(page, allow_private_networks=local, private_origins=grants, auto_dismiss_popups=False)


def _page() -> MagicMock:
    page = MagicMock()
    page.url = _TAB_URL
    page.goto = AsyncMock()
    return page


def _lists(*, block: tuple[str, ...] = (), allow: tuple[str, ...] = ()) -> DomainListPolicy:
    return DomainListPolicy(DomainAllowlist.from_strings(allow), DomainAllowlist.from_strings(block))


class TestAdmission:
    @pytest.mark.asyncio
    async def test_the_cloud_policy_resolves_and_pins_the_host(self) -> None:
        with patch(_PIN, new_callable=AsyncMock) as pin:
            await _navigator(_page()).admit_download("https://example.com/f.bin")

        pin.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["http://127.0.0.1:8080/f.bin", "http://169.254.169.254/latest/meta-data/"])
    async def test_the_cloud_policy_refuses_private_and_metadata_addresses(self, url: str) -> None:
        with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
            await _navigator(_page()).admit_download(url)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        ["javascript:void(fetch('/x'))", "file:///etc/passwd", "data:text/plain,hi", "blob:https://a.test/1"],
    )
    async def test_a_scheme_that_is_not_a_network_scheme_is_refused(self, url: str) -> None:
        with pytest.raises(BrowserNavigationBlockedError, match="Unsupported navigation scheme"):
            await _navigator(_page()).admit_download(url)

    @pytest.mark.asyncio
    async def test_local_mode_grants_only_the_origin_the_agent_named(self) -> None:
        grants = PrivateOriginGrants()

        await _navigator(_page(), local=True, grants=grants).admit_download("http://localhost:3000/f.bin")

        assert grants.permits("http://localhost:3000/other")
        assert not grants.permits("http://localhost:3001/")

    @pytest.mark.asyncio
    async def test_local_mode_never_admits_cloud_metadata_even_when_named(self) -> None:
        with pytest.raises(BrowserNavigationBlockedError):
            await _navigator(_page(), local=True, grants=PrivateOriginGrants()).admit_download(
                "http://169.254.169.254/latest/meta-data/"
            )

    def test_local_grants_default_to_the_registry_shared_by_the_contexts_navigators(self) -> None:
        page = _page()

        assert _navigator(page, local=True)._grants() is private_origin_grants(page.context)
        assert _navigator(page)._grants() is None


class TestLanding:
    @pytest.mark.asyncio
    async def test_local_mode_refuses_another_private_origin_than_the_one_named(self) -> None:
        navigator = _navigator(_page(), local=True, grants=PrivateOriginGrants())
        await navigator.admit_download("http://localhost:3000/go")

        await navigator.assert_landed_allowed("http://localhost:3000/final.bin")
        with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
            await navigator.assert_landed_allowed("http://localhost:9999/secret")

    @pytest.mark.asyncio
    async def test_the_contexts_domain_lists_judge_the_address_the_request_ended_on(self) -> None:
        page = _page()
        bind_domain_lists(page.context, _lists(block=("bad.example",)))
        navigator = _navigator(page)

        with patch(_PIN, new_callable=AsyncMock):
            await navigator.assert_landed_allowed("https://good.example/f.bin")
            with pytest.raises(BrowserNavigationBlockedError, match="blocklist"):
                await navigator.assert_landed_allowed("https://bad.example/f.bin")

    @pytest.mark.asyncio
    async def test_a_refused_address_resets_the_tab_only_when_asked_to(self) -> None:
        page = _page()
        navigator = _navigator(page)

        with pytest.raises(BrowserNavigationBlockedError):
            await navigator.assert_landed_allowed("http://127.0.0.1:9/secret")
        page.goto.assert_not_awaited()

        with pytest.raises(BrowserNavigationBlockedError):
            await navigator.assert_landed_allowed("http://127.0.0.1:9/secret", discard_document=True)
        assert [call.args[0] for call in page.goto.await_args_list] == ["about:blank"]

    @pytest.mark.asyncio
    async def test_an_allowed_address_leaves_the_tab_alone(self) -> None:
        page = _page()

        with patch(_PIN, new_callable=AsyncMock):
            await _navigator(page).assert_landed_allowed("https://example.com/f.bin", discard_document=True)

        page.goto.assert_not_awaited()
