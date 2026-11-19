"""Real-Chromium proof that the pool refuses a page whose certificate the browser does not trust, unless asked not to.

The site presents a certificate from a private CA that no browser trusts. A pool left at its default must not open it
in any kind of context, and the Agent is told that the certificate is the problem. The same site opens when the
operator opted out or when the creator of one context asks for it, and one relaxed context does not relax its
siblings in the same browser. The verdict is judged by what the site received: a page the browser refuses never
sends it a request. Run with:
`pytest -m integration tests/toolkits/browser/pool/test_certificate_verification_integration.py`.
"""

from __future__ import annotations

import dataclasses
import ssl
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from patchright.async_api import Error as BrowserDriverError

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.exceptions import BrowserNavigationError
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from tests.support.mcp_testkit.tls_pki import generate_tls_pki
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._redirect_servers import Site, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_UNTRUSTED_ISSUER = "net::ERR_CERT_AUTHORITY_INVALID"
_PAGE_TEXT = "certificate-probe-page"
_GOTO_TIMEOUT_MS = 15_000


@pytest.fixture
def untrusted_site(tmp_path: Path) -> Iterator[Site]:
    """An HTTPS site on loopback whose certificate chains to a CA that no trust store holds."""
    pki = generate_tls_pki(tmp_path)
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain(pki.server_cert, pki.server_key)
    with serve({"/": page(_PAGE_TEXT)}, tls=server_tls) as site:
        yield site


@asynccontextmanager
async def _pool(*, ignore_https_errors: bool | None = None) -> AsyncIterator[GlobalBrowserPool]:
    """A one-browser pool; ``None`` keeps the certificate choice the config ships with, else it is the operator's."""
    config = BrowserPoolConfig.minimal()
    if ignore_https_errors is not None:
        config = dataclasses.replace(config, ignore_https_errors=ignore_https_errors)
    pool = GlobalBrowserPool(max_browsers=1, config=config)
    try:
        yield pool
    finally:
        await pool.shutdown()


async def _text_shown(
    pool: GlobalBrowserPool,
    site: Site,
    *,
    key: str,
    context_type: ContextType = ContextType.AGENT,
    context_kwargs: dict[str, object] | None = None,
) -> str:
    """The text a page of ``site`` shows in the context ``key``; raises the browser's error when it refuses the page."""
    opened, context_key = await pool.acquire_page(context_type, context_key=key, context_kwargs=context_kwargs)
    try:
        await opened.goto(site.url("/"), timeout=_GOTO_TIMEOUT_MS)
        return await opened.inner_text("body")
    finally:
        await pool.release_page(opened, context_key)


class TestDefault:
    async def test_no_kind_of_context_opens_a_page_with_an_untrusted_certificate(self, untrusted_site: Site) -> None:
        async with _pool() as pool:
            for context_type in ContextType:
                with pytest.raises(BrowserDriverError, match=_UNTRUSTED_ISSUER):
                    await _text_shown(
                        pool, untrusted_site, key=f"strict-{context_type.value}", context_type=context_type
                    )

        assert untrusted_site.paths() == []

    async def test_the_agent_is_told_that_the_certificate_is_the_problem(self, untrusted_site: Site) -> None:
        async with _pool() as pool:
            session = BrowserSession(pool, ContextType.AGENT, allow_private_networks=True)
            try:
                await session.new_tab()
                with pytest.raises(BrowserNavigationError) as refused:
                    await session.navigate(untrusted_site.url("/"))
            finally:
                await session.close()

        assert _UNTRUSTED_ISSUER in str(refused.value.diagnostic_info["error_text"])
        assert "certificate" in refused.value.recovery_suggestions[0]
        assert untrusted_site.paths() == []


class TestOperatorOptOut:
    async def test_every_kind_of_context_opens_the_page(self, untrusted_site: Site) -> None:
        async with _pool(ignore_https_errors=True) as pool:
            for context_type in ContextType:
                shown = await _text_shown(
                    pool, untrusted_site, key=f"relaxed-{context_type.value}", context_type=context_type
                )

                assert shown == _PAGE_TEXT, context_type

        assert untrusted_site.paths("GET").count("/") == len(ContextType)


class TestCreatorOfAContext:
    async def test_it_can_ask_for_the_page_under_the_default(self, untrusted_site: Site) -> None:
        async with _pool() as pool:
            shown = await _text_shown(
                pool, untrusted_site, key="asks-to-ignore", context_kwargs={"ignore_https_errors": True}
            )

        assert shown == _PAGE_TEXT

    async def test_it_can_ask_for_verification_under_the_opt_out(self, untrusted_site: Site) -> None:
        async with _pool(ignore_https_errors=True) as pool:
            with pytest.raises(BrowserDriverError, match=_UNTRUSTED_ISSUER):
                await _text_shown(
                    pool, untrusted_site, key="asks-to-verify", context_kwargs={"ignore_https_errors": False}
                )

        assert untrusted_site.paths() == []

    async def test_a_relaxed_context_leaves_its_sibling_in_the_same_browser_strict(self, untrusted_site: Site) -> None:
        async with _pool() as pool:
            relaxed = await _text_shown(
                pool, untrusted_site, key="relaxed", context_kwargs={"ignore_https_errors": True}
            )
            assert relaxed == _PAGE_TEXT
            requests_so_far = len(untrusted_site.hits)

            with pytest.raises(BrowserDriverError, match=_UNTRUSTED_ISSUER):
                await _text_shown(pool, untrusted_site, key="sibling")

        assert len(untrusted_site.hits) == requests_so_far
