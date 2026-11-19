"""L1 HTTP fetcher via Scrapling curl_cffi.

[INPUT]
- .bounded_get::bounded_get (POS: a GET through Scrapling whose body is held to a size bound while it is received, connecting only to the addresses it is given)
- .target_guard::FetchTargetGuard (POS: per-fetch SSRF policy and network blocklist for the web_fetch tiers)
- toolkits.web_fetch.processing.charset_detector::detect_and_decode_html (POS: Multi-tier charset detection)
- toolkits.browser.pool.proxy::ProxyPool (POS: Proxy rotation pool for FetchEngine)
- utils.content_sniff::classify_payload (POS: web page, text or binary file, decided once for every fetch tier)

[OUTPUT]
- HttpFetcher: L1 tier fetcher; every hop (the requested URL and each redirect ``Location``) is judged and dialed in its canonical spelling, at the addresses the judgment looked at, and a hop the SSRF policy or the network blocklist rejects raises SSRFSecurityError instead of degrading to the next tier

[POS]
L1 lightweight HTTP fetcher. Delegates TLS impersonation to Scrapling defaults.
Every body is received through ``bounded_get``, so one response never holds more than the transfer bound.
"""

from __future__ import annotations

import asyncio
import http.cookiejar
import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.core.security.http.secure_fetch import (
    is_ssrf_shield_enabled,
    parse_allowed_internal_hosts,
)
from myrm_agent_harness.toolkits.web_fetch.processing.charset_detector import detect_and_decode_html
from myrm_agent_harness.utils.content_sniff import PayloadKind, classify_payload

from .bounded_get import FetchedResponse, bounded_get
from .protocols import FetcherType, FetchResult
from .target_guard import FetchTargetGuard

if TYPE_CHECKING:
    from scrapling.engines._browsers._types import GetRequestParams  # type: ignore[import-untyped, unused-ignore]

    from myrm_agent_harness.toolkits.browser.pool.proxy import ProxyPool
    from myrm_agent_harness.toolkits.browser.session_vault import SessionVault

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_MAX_CONCURRENT = 20
_MAX_REDIRECTS = 5


# A readable body is cut where reading further stops paying off. A web page is converted to Markdown on one CPU-bound
# thread (about a second per 750 KB), so its ceiling is low. Text is kept as it is and costs milliseconds, so its
# ceiling follows what a stored copy of a page can hold (2,000,000 characters). A truncated PDF or Office file cannot
# be parsed, so file bodies stay whole up to the transfer bound, which is the binary router's size limit: the router
# drops a file that arrives one byte over it.
MAX_HTML_BODY_BYTES = 750_000
MAX_PLAIN_TEXT_BODY_BYTES = 2_000_000


class HttpFetcher:
    """L1 tier: curl_cffi HTTP requests, TLS fingerprint spoofing"""

    fetcher_type = FetcherType.HTTP

    def __init__(
        self,
        max_concurrent: int = _MAX_CONCURRENT,
        timeout: int = _DEFAULT_TIMEOUT,
        proxy_pool: ProxyPool | None = None,
        session_vault: SessionVault | None = None,
        allow_private_networks: bool = False,
        network_blocklist: tuple[str, ...] = (),
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout
        self._proxy_pool = proxy_pool
        self._session_vault = session_vault
        self._allow_private_networks = allow_private_networks
        self._network_blocklist = network_blocklist

    async def fetch(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> FetchResult | None:
        enable_ssrf_shield = is_ssrf_shield_enabled()
        allowed_hosts = parse_allowed_internal_hosts()

        headers: dict[str, str] = {}
        domain = self._extract_domain(url)
        from ..extractors.weixin_extractor import get_weixin_request_headers

        headers.update(get_weixin_request_headers(domain))
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        cookie_jar = await self._load_cookie_jar(url)

        async with self._semaphore:
            return await self._fetch_with_redirects(
                url,
                headers=headers,
                cookie_jar=cookie_jar,
                enable_ssrf_shield=enable_ssrf_shield,
                allowed_hosts=allowed_hosts,
            )

    @staticmethod
    def _extract_domain(url: str) -> str:
        hostname = (urlparse(url).hostname or "").lower()
        if hostname.startswith("www."):
            return hostname[4:]
        return hostname

    async def _load_cookie_jar(self, url: str) -> http.cookiejar.CookieJar | None:
        if not self._session_vault:
            return None

        try:
            domain = self._extract_domain(url)
            entry = await self._session_vault.load(domain)
            if not entry or not entry.storage_state or "cookies" not in entry.storage_state:
                return None

            cookie_jar = http.cookiejar.CookieJar()
            for cookie in entry.storage_state["cookies"]:
                c_domain = cookie.get("domain", "")
                c_path = cookie.get("path", "/")
                c_secure = cookie.get("secure", False)
                c_expires = cookie.get("expires")
                if c_expires in (-1, 0, None):
                    c_expires = None

                cookie_jar.set_cookie(
                    http.cookiejar.Cookie(
                        version=0,
                        name=cookie["name"],
                        value=cookie["value"],
                        port=None,
                        port_specified=False,
                        domain=c_domain,
                        domain_specified=bool(c_domain),
                        domain_initial_dot=c_domain.startswith("."),
                        path=c_path,
                        path_specified=bool(c_path),
                        secure=c_secure,
                        expires=c_expires,
                        discard=False,
                        comment=None,
                        comment_url=None,
                        rest={"HttpOnly": cookie.get("httpOnly", False)},
                        rfc2109=False,
                    )
                )
            return cookie_jar
        except Exception as exc:
            logger.warning("HttpFetcher failed to load session cookies for %s: %s", url, exc)
            return None

    async def _fetch_with_redirects(
        self,
        url: str,
        *,
        headers: dict[str, str],
        cookie_jar: http.cookiejar.CookieJar | None,
        enable_ssrf_shield: bool,
        allowed_hosts: list[str],
    ) -> FetchResult | None:
        current_url = url
        redirect_count = 0
        guard = FetchTargetGuard.for_fetch(
            url,
            allow_private_networks=self._allow_private_networks,
            allowed_hosts=allowed_hosts,
            ssrf_shield=enable_ssrf_shield,
            network_blocklist=self._network_blocklist,
        )

        while redirect_count <= _MAX_REDIRECTS:
            addresses: tuple[str, ...] = ()
            if guard is not None:
                # A rejected hop raises SSRFSecurityError: returning None would let the browser tiers
                # fetch the same URL. The hop is judged and dialed in its canonical spelling, because
                # libcurl may read another spelling as a different host than the one the policy classified,
                # and it connects only to the addresses the judgment looked at: it does not resolve the
                # name again, and the URL keeps the name so the certificate is checked against it.
                current_url = guard.canonical_url(current_url)
                addresses = await guard.pin(current_url)

            try:
                response = await bounded_get(current_url, self._build_request_kwargs(headers, cookie_jar), addresses)

                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location") or response.headers.get("location")
                    if not location:
                        break
                    current_url = urljoin(current_url, location)
                    redirect_count += 1
                    continue

                return self._response_to_fetch_result(response, current_url)
            except SSRFSecurityError:
                raise
            except Exception as exc:
                logger.warning("HttpFetcher failed at %s — %s", current_url, exc)
                return None

        logger.warning("HttpFetcher failed: Too many redirects (%s) for %s", _MAX_REDIRECTS, url)
        return None

    def _build_request_kwargs(
        self,
        headers: dict[str, str],
        cookie_jar: http.cookiejar.CookieJar | None,
    ) -> GetRequestParams:
        kwargs: GetRequestParams = {
            "timeout": self._timeout,
            "follow_redirects": False,
        }

        if headers:
            kwargs["headers"] = headers.copy()

        if self._proxy_pool:
            kwargs["proxy"] = self._proxy_pool.get_next().to_url()

        if cookie_jar is not None:
            kwargs["cookies"] = cookie_jar

        return kwargs

    @staticmethod
    def _response_to_fetch_result(response: FetchedResponse, current_url: str) -> FetchResult:
        status = response.status
        resp_headers = response.headers
        response_url = response.url or current_url

        if status == 304:
            return FetchResult(
                html="",
                url=response_url,
                status_code=304,
                headers=resp_headers,
                fetcher_type=FetcherType.HTTP,
            )

        body = response.body
        encoding = response.encoding
        kind = classify_payload(resp_headers.get("content-type"), body)

        if kind is not PayloadKind.BINARY:
            ceiling = MAX_HTML_BODY_BYTES if kind is PayloadKind.WEB else MAX_PLAIN_TEXT_BODY_BYTES
            source_truncated = len(body) > ceiling
            if source_truncated:
                logger.warning("L1 HTTP response body capped: %d -> %d bytes for %s", len(body), ceiling, current_url)
                body = body[:ceiling]
            # The cut can leave half a character at the end; decoding it as partial keeps that from failing the decode.
            html, _detected_enc = detect_and_decode_html(body, encoding, partial=source_truncated)
            return FetchResult(
                html=html,
                url=response_url,
                status_code=status,
                headers=resp_headers,
                fetcher_type=FetcherType.HTTP,
                kind=kind,
                source_truncated=source_truncated,
            )

        return FetchResult(
            html="",
            url=response_url,
            status_code=status,
            headers=resp_headers,
            fetcher_type=FetcherType.HTTP,
            raw_body=body,
        )

    async def shutdown(self) -> None:
        pass
