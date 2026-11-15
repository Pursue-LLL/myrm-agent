"""The user's network blocklist holds for every URL a web_fetch request reaches, redirect hops included.

A listed host is never read. The HTTP tier judges the requested URL and every redirect hop before it is requested
(real curl_cffi against loopback servers: what was never requested proves the verdict). A remote escalation
provider is judged by the URL it reports. A verdict is terminal: no other tier tries the URL, and the failure is
remembered. The browser and stealth tiers are in ``test_network_blocklist_browser_tiers.py``, the tool wiring in
``test_network_blocklist_tool.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.core.security.audit import get_audit_entries, reset_audit_log
from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.escalation.metrics import web_fetch_escalation_metrics
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard import (
    FetchTargetGuard,
    NetworkBlocklistError,
    assert_not_blocklisted,
)
from myrm_agent_harness.toolkits.web_fetch.processing.url_normalizer import normalize_url
from tests.toolkits.browser._redirect_servers import Site, page, redirect, serve

# Scrapling builds its lxml parser with an option lxml now warns about; the project turns warnings into errors.
pytestmark = pytest.mark.filterwarnings("ignore:The 'strip_cdata' option")

_GUARD = "myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard"
_DISPATCH = "myrm_agent_harness.toolkits.web_fetch.engine.fetch_mixin"
_ARTICLE = "<article><p>" + "reachable-body " * 40 + "</p></article>"  # enough markup to not read as an empty shell


@dataclass(slots=True)
class _Tiers:
    browser: AsyncMock
    stealth: AsyncMock

    def untouched(self) -> bool:
        return not self.browser.await_count and not self.stealth.await_count


def _engine(*, blocklist: tuple[str, ...]) -> tuple[FetchEngine, _Tiers]:
    """A local-mode engine whose browser and stealth tiers are spies: a URL that reaches one escaped the verdict."""
    engine = FetchEngine(allow_private_networks=True, network_blocklist=blocklist)
    tiers = _Tiers(browser=AsyncMock(return_value=None), stealth=AsyncMock(return_value=None))
    engine._browser_fetcher.fetch = tiers.browser  # type: ignore[method-assign]
    engine._stealth_fetcher.fetch = tiers.stealth  # type: ignore[method-assign]
    return engine, tiers


@contextmanager
def _redirect_chain() -> Iterator[tuple[Site, Site]]:
    """``entry`` (127.0.0.1) redirects to ``internal``, which the redirect spells with the host name ``localhost``."""
    with serve({"/secret": page(_ARTICLE)}) as internal:
        port = internal.base_url.rsplit(":", 1)[1]
        with serve({"/start": redirect(f"http://localhost:{port}/secret")}) as entry:
            yield entry, internal


class TestAssertNotBlocklisted:
    @pytest.mark.parametrize(
        ("url", "blocklist"),
        [
            ("https://blocked.example/a", ("blocked.example",)),
            ("https://BLOCKED.example./a", ("blocked.example",)),  # case and the trailing dot
            ("https://sub.blocked.example/", ("*.blocked.example",)),
            ("https://blocked.example/", ("*.blocked.example",)),  # a wildcard covers its apex
            ("http://xn--bcher-kva.example/", ("bücher.example",)),  # Punycode URL, Unicode entry
            ("http://bücher.example/", ("xn--bcher-kva.example",)),
            ("http://2130706433:8080/", ("127.0.0.1",)),  # the address a legacy spelling dials
            ("http://0x7f.1/", ("127.0.0.1",)),
            ("https://ok.example/", ("other.example", "ok.example")),  # anywhere in the list
        ],
    )
    def test_a_listed_host_is_refused_in_whatever_spelling_a_client_dials(
        self, url: str, blocklist: tuple[str, ...]
    ) -> None:
        with pytest.raises(NetworkBlocklistError):
            assert_not_blocklisted(url, blocklist)

    @pytest.mark.parametrize(
        ("url", "blocklist"),
        [
            ("https://blocked.example.org/", ("blocked.example",)),
            ("https://sub.blocked.example/", ("blocked.example",)),  # a plain entry is exact
            ("https://notblocked.example/", ("*.blocked.example",)),  # a wildcard stops at the label
            ("https://blocked.example/", ()),
            ("https://example.com/?next=blocked.example", ("blocked.example",)),  # only the host counts
        ],
    )
    def test_other_hosts_are_admitted(self, url: str, blocklist: tuple[str, ...]) -> None:
        assert_not_blocklisted(url, blocklist)

    def test_an_empty_list_admits_even_a_url_with_no_canonical_spelling(self) -> None:
        assert_not_blocklisted("http://localhost:99999/", ())

    def test_a_url_with_no_canonical_spelling_cannot_be_judged_and_is_refused(self) -> None:
        with pytest.raises(SSRFSecurityError) as refused:
            assert_not_blocklisted("http://localhost:99999/", ("blocked.example",))

        assert not isinstance(refused.value, NetworkBlocklistError)

    def test_the_verdict_is_a_terminal_ssrf_class_error_that_names_the_domain(self) -> None:
        with pytest.raises(SSRFSecurityError, match=re.escape("Domain 'blocked.example' is blocked by policy")):
            assert_not_blocklisted("https://blocked.example/a", ("blocked.example",))

    def test_the_verdict_is_audited_with_the_host_and_never_the_url(self) -> None:
        reset_audit_log()

        with pytest.raises(NetworkBlocklistError):
            assert_not_blocklisted("https://blocked.example/a?token=s3cr3t", ("blocked.example",))

        [entry] = get_audit_entries()
        assert (entry.tool_name, entry.decision) == ("web_fetch", "DENY")
        assert "blocked.example" in entry.reason
        assert "s3cr3t" not in entry.reason


@pytest.mark.asyncio
class TestFetchTargetGuard:
    @staticmethod
    def _guard(*, shield: bool, blocklist: tuple[str, ...]) -> FetchTargetGuard | None:
        return FetchTargetGuard.for_fetch(
            "https://start.example/",
            allow_private_networks=False,
            allowed_hosts=[],
            ssrf_shield=shield,
            network_blocklist=blocklist,
        )

    async def test_a_fetch_with_neither_shield_nor_list_needs_no_guard(self) -> None:
        assert self._guard(shield=False, blocklist=()) is None

    @pytest.mark.parametrize("shield", [True, False])
    async def test_a_listed_hop_is_refused_before_any_name_lookup(self, shield: bool) -> None:
        guard = self._guard(shield=shield, blocklist=("blocked.example",))
        assert guard is not None
        lookup = AsyncMock(side_effect=AssertionError("the name was resolved"))

        with patch(f"{_GUARD}.async_pin_url", new=lookup), pytest.raises(NetworkBlocklistError):
            await guard.pin("https://blocked.example/x")

    async def test_with_the_shield_off_an_unlisted_hop_is_requested_as_written(self) -> None:
        guard = self._guard(shield=False, blocklist=("blocked.example",))
        assert guard is not None

        assert await guard.pin("https://fine.example/x") == ("https://fine.example/x", {})

    async def test_with_the_shield_on_an_unlisted_hop_still_gets_the_ssrf_policy(self) -> None:
        guard = self._guard(shield=True, blocklist=("blocked.example",))
        assert guard is not None
        pinned = AsyncMock(return_value=("https://93.184.216.34/x", {"Host": "fine.example"}))

        with patch(f"{_GUARD}.async_pin_url", new=pinned):
            assert await guard.pin("https://fine.example/x") == ("https://93.184.216.34/x", {"Host": "fine.example"})

        pinned.assert_awaited_once()


@pytest.mark.asyncio
class TestHttpTierOnLoopbackServers:
    """The SSRF policy admits ``localhost`` as a redirect target, so only the blocklist can refuse it."""

    @pytest.fixture(autouse=True)
    def _admit_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_ALLOWED_INTERNAL_HOSTS", "localhost")

    async def test_the_chain_is_followed_when_nothing_is_listed(self) -> None:
        engine, _tiers = _engine(blocklist=())

        with _redirect_chain() as (entry, internal):
            doc = await engine.crawl(entry.url("/start"), allow_escalation=False)

        assert doc is not None
        assert internal.paths() == ["/secret"]

    @pytest.mark.parametrize(
        "entries",
        [("localhost",), ("*.localhost",), ("other.example", "localhost")],
        ids=["exact", "wildcard", "among-others"],
    )
    async def test_a_redirect_to_a_listed_host_is_never_requested_and_does_not_degrade(
        self, entries: tuple[str, ...]
    ) -> None:
        engine, tiers = _engine(blocklist=entries)

        with _redirect_chain() as (entry, internal):
            doc = await engine.crawl(entry.url("/start"), allow_escalation=False)

        assert doc is None
        assert entry.paths() == ["/start"]
        assert internal.hits == []
        assert tiers.untouched()

    async def test_a_listed_requested_url_is_refused_without_a_request(self) -> None:
        engine, tiers = _engine(blocklist=("127.0.0.1",))

        with _redirect_chain() as (entry, internal):
            doc = await engine.crawl(entry.url("/start"), allow_escalation=False)

        assert doc is None
        assert entry.hits == []
        assert internal.hits == []
        assert tiers.untouched()

    async def test_the_http_tier_raises_so_that_no_other_tier_tries_the_url(self) -> None:
        fetcher = HttpFetcher(allow_private_networks=True, network_blocklist=("localhost",))

        with _redirect_chain() as (entry, internal), pytest.raises(NetworkBlocklistError):
            await fetcher.fetch(entry.url("/start"))

        assert internal.hits == []

    async def test_the_list_holds_with_the_ssrf_shield_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_ENABLE_SSRF_SHIELD", "false")
        fetcher = HttpFetcher(allow_private_networks=True, network_blocklist=("localhost",))

        with _redirect_chain() as (entry, internal), pytest.raises(NetworkBlocklistError):
            await fetcher.fetch(entry.url("/start"))

        assert internal.hits == []

    async def test_a_refused_url_is_remembered_as_failed(self) -> None:
        engine, _tiers = _engine(blocklist=("localhost",))

        with _redirect_chain() as (entry, _internal):
            start = entry.url("/start")
            await engine.crawl(start, allow_escalation=False)

        assert engine._fail_cache.contains(normalize_url(start))


@pytest.mark.asyncio
class TestEngine:
    async def test_the_engine_hands_its_list_to_every_tier(self) -> None:
        engine = FetchEngine(network_blocklist=("a.example", "*.b.example"))

        assert engine._http_fetcher._network_blocklist == ("a.example", "*.b.example")
        assert engine._browser_fetcher._network_blocklist == ("a.example", "*.b.example")
        assert engine._stealth_fetcher._network_blocklist == ("a.example", "*.b.example")

    async def test_a_listed_platform_url_never_reaches_its_fast_path(self) -> None:
        engine = FetchEngine(network_blocklist=("www.youtube.com",))

        with patch(f"{_DISPATCH}.extract_youtube_transcript", new_callable=AsyncMock) as transcript:
            assert await engine.crawl("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None

        transcript.assert_not_awaited()

    @staticmethod
    def _provider(url: str | None, content: str = "# page") -> SimpleNamespace:
        return SimpleNamespace(
            provider_id="remote",
            fetch_url=AsyncMock(return_value=SimpleNamespace(content=content, is_markdown=True, url=url, title="t")),
        )

    async def test_a_provider_reporting_a_listed_url_ends_the_fetch_for_every_provider(self) -> None:
        engine = FetchEngine(network_blocklist=("listed.example",))
        reports_listed = self._provider("https://listed.example/landing")
        next_in_line = self._provider(None, content="# other")
        engine.set_escalation_providers([reports_listed, next_in_line])
        failures_before = web_fetch_escalation_metrics.snapshot()["failure_count"]

        with pytest.raises(NetworkBlocklistError):
            await engine._try_escalation("https://start.example/a")

        next_in_line.fetch_url.assert_not_awaited()
        assert web_fetch_escalation_metrics.snapshot()["failure_count"] == failures_before + 1

    async def test_a_provider_reporting_no_url_is_judged_by_the_requested_one(self) -> None:
        engine = FetchEngine(network_blocklist=("listed.example",))
        engine.set_escalation_providers([self._provider(None)])

        doc, _result = await engine._try_escalation("https://start.example/a")

        assert doc is not None
        assert doc.page_content == "# page"

    async def test_through_crawl_a_listed_report_is_a_failed_fetch_that_is_remembered(self) -> None:
        engine = FetchEngine(allow_private_networks=True, network_blocklist=("listed.example",))
        for tier in (engine._http_fetcher, engine._browser_fetcher, engine._stealth_fetcher):
            tier.fetch = AsyncMock(return_value=None)  # type: ignore[method-assign]
        engine.set_escalation_providers([self._provider("https://listed.example/landing")])

        assert await engine.crawl("https://start.example/a") is None
        assert engine._fail_cache.contains(normalize_url("https://start.example/a"))
