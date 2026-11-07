"""The HTTP tier connects to the host its SSRF policy judged: every hop is requested in its canonical spelling.

A client can read a spelling of a host (a zero-width joiner inside a label, legacy numeric IPv4, ...) as another host
than the one the policy classified. The tier therefore judges and requests the canonical URL, on the entry hop and on
every redirect ``Location``, under both policies, and a hop with no canonical spelling is refused before it is sent.
``AsyncFetcher.get`` is the boundary: the URL it receives is the one the client dials. The real clients are asked about
the same spellings in ``tests/utils/test_url_syntax_libcurl.py``.
"""

from __future__ import annotations

import ipaddress
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from myrm_agent_harness.utils.url_syntax import parse_outbound_url
from tests.support.host_spellings import DIAL_SPELLINGS

_PIN = "myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard.async_pin_url"
_LOOKUP = "myrm_agent_harness.core.security.redirect_hop_guard.hop_evaluator.resolve_addresses"
# ``urljoin`` rejects a bracketed host that is not an IP literal, so a redirect to it is never followed.
_REDIRECT_SPELLINGS = tuple(spelling for spelling in DIAL_SPELLINGS if spelling != "[example.test]")
_NO_CANONICAL_SPELLING = ["http://example.test\\@evil.test/", "http://exam%70le.test/", "http://example.test:99999/"]


def _canonical(url: str) -> str:
    target, error = parse_outbound_url(url)
    assert target is not None, f"{url!r} has no canonical spelling ({error})"
    return target.url


def _response(location: str | None = None) -> MagicMock:
    response = MagicMock()
    response.status = 302 if location else 200
    response.headers = {"Location": location} if location else {"content-type": "text/html"}
    response.body = ("<article><p>" + "x" * 300 + "</p></article>").encode()
    response.encoding = "utf-8"
    response.url = ""  # the result is attributed to the URL the tier requested
    return response


async def _fetch(fetcher: HttpFetcher, url: str, *, shield: bool = True) -> FetchResult | None:
    return await fetcher._fetch_with_redirects(
        url, headers={}, cookie_jar=None, enable_ssrf_shield=shield, allowed_hosts=[], use_http3=False
    )


def _requested(get: AsyncMock) -> list[str]:
    return [call.args[0] for call in get.await_args_list]


@pytest.fixture
def local_fetcher(monkeypatch: pytest.MonkeyPatch) -> HttpFetcher:
    """A fetcher under the local policy whose name lookups answer a public address, so no test touches the network."""

    async def answer(_hostname: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return (ipaddress.ip_address("93.184.216.34"),)

    monkeypatch.setattr(_LOOKUP, answer)
    return HttpFetcher(allow_private_networks=True)


@pytest.fixture
def judged(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The cloud policy's pin, replaced by a recorder of the URLs it was asked to judge (it would resolve names)."""
    seen: list[str] = []

    async def pin(url: str, _allowed_hosts: list[str]) -> tuple[str, dict[str, str]]:
        seen.append(url)
        return url, {}

    monkeypatch.setattr(_PIN, pin)
    return seen


@pytest.mark.asyncio
class TestEveryHopIsRequestedInItsCanonicalSpelling:
    @pytest.mark.parametrize("spelling", DIAL_SPELLINGS)
    async def test_the_requested_url_under_the_local_policy(
        self, local_fetcher: HttpFetcher, install_fake_scrapling: AsyncMock, spelling: str
    ) -> None:
        url = f"http://{spelling}/page"
        install_fake_scrapling.return_value = _response()

        await _fetch(local_fetcher, url)

        assert _requested(install_fake_scrapling) == [_canonical(url)]

    @pytest.mark.parametrize("spelling", _REDIRECT_SPELLINGS)
    async def test_a_redirect_location_under_the_local_policy(
        self, local_fetcher: HttpFetcher, install_fake_scrapling: AsyncMock, spelling: str
    ) -> None:
        """The entry origin is granted in its canonical spelling, so a private spelling of it stays reachable."""
        target = _canonical(f"http://{spelling}/page")
        install_fake_scrapling.side_effect = [_response(f"http://{spelling}/next"), _response()]

        await _fetch(local_fetcher, target)

        assert _requested(install_fake_scrapling) == [target, _canonical(f"http://{spelling}/next")]

    @pytest.mark.parametrize("spelling", DIAL_SPELLINGS)
    async def test_the_requested_url_under_the_cloud_policy(
        self, install_fake_scrapling: AsyncMock, judged: list[str], spelling: str
    ) -> None:
        url = f"http://{spelling}/page"
        install_fake_scrapling.return_value = _response()

        await _fetch(HttpFetcher(), url)

        assert judged == _requested(install_fake_scrapling) == [_canonical(url)]

    @pytest.mark.parametrize("spelling", _REDIRECT_SPELLINGS)
    async def test_a_redirect_location_under_the_cloud_policy(
        self, install_fake_scrapling: AsyncMock, judged: list[str], spelling: str
    ) -> None:
        install_fake_scrapling.side_effect = [_response(f"http://{spelling}/next"), _response()]

        await _fetch(HttpFetcher(), "http://example.test/page")

        expected = ["http://example.test/page", _canonical(f"http://{spelling}/next")]
        assert judged == _requested(install_fake_scrapling) == expected

    async def test_the_fetch_result_is_attributed_to_the_canonical_url(
        self, local_fetcher: HttpFetcher, install_fake_scrapling: AsyncMock
    ) -> None:
        install_fake_scrapling.return_value = _response()

        result = await _fetch(local_fetcher, "http://EXAMPLE.test./page")

        assert result is not None
        assert result.url == "http://example.test/page"

    async def test_a_relative_redirect_continues_from_the_canonical_url(
        self, local_fetcher: HttpFetcher, install_fake_scrapling: AsyncMock
    ) -> None:
        install_fake_scrapling.side_effect = [_response("/next"), _response()]

        await _fetch(local_fetcher, "http://EXAMPLE.test./page")

        assert _requested(install_fake_scrapling) == ["http://example.test/page", "http://example.test/next"]

    async def test_the_name_dialed_after_a_failed_pinned_request_is_the_canonical_one(
        self, install_fake_scrapling: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def pin(url: str, _allowed_hosts: list[str]) -> tuple[str, dict[str, str]]:
            return "http://203.0.113.9/page", {"Host": "example.test"}

        monkeypatch.setattr(_PIN, pin)
        install_fake_scrapling.side_effect = [OSError("certificate names the host, not the address"), _response()]

        await _fetch(HttpFetcher(), "http://EXAMPLE.test./page")

        assert _requested(install_fake_scrapling) == ["http://203.0.113.9/page", "http://example.test/page"]

    async def test_a_fetch_without_the_shield_requests_the_url_as_written(
        self, install_fake_scrapling: AsyncMock
    ) -> None:
        install_fake_scrapling.return_value = _response()

        await _fetch(HttpFetcher(), "http://EXAMPLE.test./page", shield=False)

        assert _requested(install_fake_scrapling) == ["http://EXAMPLE.test./page"]


@pytest.mark.asyncio
class TestAUrlWithNoCanonicalSpellingIsRefusedBeforeItIsSent:
    @pytest.mark.parametrize("url", _NO_CANONICAL_SPELLING)
    async def test_the_requested_url_under_the_local_policy(
        self, local_fetcher: HttpFetcher, install_fake_scrapling: AsyncMock, url: str
    ) -> None:
        with pytest.raises(SSRFSecurityError):
            await _fetch(local_fetcher, url)

        install_fake_scrapling.assert_not_awaited()

    @pytest.mark.parametrize("url", _NO_CANONICAL_SPELLING)
    async def test_a_redirect_location_under_the_local_policy(
        self, local_fetcher: HttpFetcher, install_fake_scrapling: AsyncMock, url: str
    ) -> None:
        install_fake_scrapling.side_effect = [_response(url)]

        with pytest.raises(SSRFSecurityError):
            await _fetch(local_fetcher, "http://example.test/start")

        assert _requested(install_fake_scrapling) == ["http://example.test/start"]

    @pytest.mark.parametrize("url", _NO_CANONICAL_SPELLING)
    async def test_the_requested_url_under_the_cloud_policy(
        self, install_fake_scrapling: AsyncMock, judged: list[str], url: str
    ) -> None:
        with pytest.raises(SSRFSecurityError):
            await _fetch(HttpFetcher(), url)

        assert judged == []
        install_fake_scrapling.assert_not_awaited()

    @pytest.mark.parametrize("url", _NO_CANONICAL_SPELLING)
    async def test_a_redirect_location_under_the_cloud_policy(
        self, install_fake_scrapling: AsyncMock, judged: list[str], url: str
    ) -> None:
        install_fake_scrapling.side_effect = [_response(url)]

        with pytest.raises(SSRFSecurityError):
            await _fetch(HttpFetcher(), "http://example.test/start")

        assert judged == ["http://example.test/start"]
        assert _requested(install_fake_scrapling) == ["http://example.test/start"]
