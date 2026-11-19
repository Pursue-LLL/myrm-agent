"""Real-Chromium proof that a pool with an egress guard connects only to addresses the SSRF policy admits.

The same page runs against a pool without the guard, which shows what a page can reach (all eight requests of the
attack page land on the internal site), and against a pool with it, where none does. The guard is judged by what the
internal site received, never by what the browser reports. The page, redirect hop, subresource, script-started request
and name that was never judged are all just connections to it. Run with:
`pytest -m integration tests/toolkits/browser/pool/test_egress_guard_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from patchright.async_api import Browser, BrowserContext, Page
from patchright.async_api import Error as BrowserDriverError

from myrm_agent_harness.toolkits.browser.pool import (
    BrowserPoolConfig,
    ContextType,
    EgressGuard,
    EgressGuardError,
    GlobalBrowserPool,
)
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._egress_world import (
    ATTACK_PATHS,
    INTERNAL_MARKER,
    PUBLIC_HOST,
    PUBLIC_MARKER,
    REBIND_HOST,
    UdpListener,
    attack_world,
    launch_options_without_guard,
    table_resolver,
)
from tests.toolkits.browser._fake_dns import process_dns, url_on
from tests.toolkits.browser._redirect_servers import redirect, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_SETTLE_S = 1.5  # the attack page starts its requests after load; a request that never arrives needs a wait to prove it
_REFUSED_BY_GUARD = "net::ERR_SOCKS_CONNECTION_FAILED"
_GUARD_GONE = "net::ERR_PROXY_CONNECTION_FAILED"
_WEBRTC_FLAG = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"


@asynccontextmanager
async def _pool(
    guard: EgressGuard | None, *, config: BrowserPoolConfig | None = None
) -> AsyncIterator[GlobalBrowserPool]:
    """A one-browser pool; without a guard its Chromium dials the fake names itself."""
    pool = GlobalBrowserPool(
        max_browsers=1,
        config=config or BrowserPoolConfig.minimal(),
        launch_options=None if guard is not None else launch_options_without_guard(),
        egress_guard=guard,
    )
    try:
        yield pool
    finally:
        await pool.shutdown()


async def _visit(pool: GlobalBrowserPool, url: str) -> str:
    """Open ``url`` in a pooled page, let the requests it starts settle, and return what the page shows."""
    page, context_key = await pool.acquire_page(ContextType.CRAWL)
    try:
        await page.goto(url)
        await asyncio.sleep(_SETTLE_S)
        return await page.content()
    finally:
        await pool.release_page(page, context_key)


async def _goto_error(page: Page, url: str) -> str:
    """The driver's error for a navigation that must fail ("" when it loaded)."""
    try:
        await page.goto(url)
    except BrowserDriverError as error:
        return str(error)
    return ""


class TestWhatTheGuardStops:
    async def test_without_the_guard_every_request_of_the_attack_page_reaches_the_internal_site(self) -> None:
        with attack_world() as world:
            async with _pool(None) as pool:
                await _visit(pool, world.public_url())

            assert set(world.internal.paths()) == set(ATTACK_PATHS)

    async def test_through_the_guard_none_of_them_does_and_the_public_page_loads_whole(self) -> None:
        guard = EgressGuard(table_resolver)
        with attack_world() as world:
            async with _pool(guard) as pool:
                html = await _visit(pool, world.public_url())

            assert PUBLIC_MARKER in html
            assert {"/", "/own.js", "/hop"} <= set(world.public.paths())
            assert world.internal.hits == []
            assert guard.handled >= len(ATTACK_PATHS)  # every request of the page was judged, none ignored

    @pytest.mark.parametrize("target", ["literal", "name", "redirect"])
    async def test_a_navigated_document_cannot_reach_it_either(self, target: str) -> None:
        """The browser loads a document itself, through the same guard as every subresource."""
        guard = EgressGuard(table_resolver)
        with attack_world() as world:
            url = {
                "literal": f"{world.internal_literal}/secret",
                "name": world.public_url("/secret", host=REBIND_HOST),
                "redirect": world.public_url("/hop-document"),
            }[target]
            async with _pool(guard) as pool:
                page, context_key = await pool.acquire_page(ContextType.CRAWL)
                try:
                    assert _REFUSED_BY_GUARD in await _goto_error(page, url)
                finally:
                    await pool.release_page(page, context_key)

            assert world.internal.hits == []

    @pytest.mark.parametrize("literal", ["127.0.0.1", "localhost", "[::1]", "169.254.169.254", "10.0.0.5", "[fe80::1]"])
    async def test_a_redirect_to_a_literal_internal_address_reaches_the_guard_and_is_refused(
        self, literal: str
    ) -> None:
        """Chromium has no implicit proxy bypass for loopback and link-local literals: every spelling is judged by the guard."""
        asked: list[str] = []

        def resolver(host: str, port: int) -> tuple[str, ...]:
            asked.append(host)
            return table_resolver(host, port)

        with serve({"/hop": redirect(f"http://{literal}:8003/")}) as site:
            async with _pool(EgressGuard(resolver)) as pool:
                page, context_key = await pool.acquire_page(ContextType.CRAWL)
                try:
                    assert _REFUSED_BY_GUARD in await _goto_error(page, url_on(PUBLIC_HOST, site, "/hop"))
                finally:
                    await pool.release_page(page, context_key)

        assert literal.strip("[]") in asked

    async def test_contexts_created_by_warmup_are_guarded_too(self) -> None:
        guard = EgressGuard(table_resolver)
        with attack_world() as world:
            async with _pool(guard) as pool:
                await pool.warmup(browsers=1, pages_per_context=1)
                contexts = pool._browsers[0].contexts
                assert set(contexts) >= {"crawl_warmup", "agent_warmup"}
                for context in contexts.values():
                    internal = await context.new_page()
                    assert _REFUSED_BY_GUARD in await _goto_error(internal, f"{world.internal_literal}/secret")
                    public = await context.new_page()  # a page that failed to load stays on Chromium's error page
                    assert await _goto_error(public, world.public_url("/plain")) == ""

            assert world.internal.hits == []

    async def test_the_guard_sits_next_to_the_default_request_filter(self) -> None:
        """The default pool config filters requests in the driver as well; neither refuses a public page."""
        guard = EgressGuard(table_resolver)
        with attack_world() as world, process_dns({PUBLIC_HOST: "93.184.216.34"}):
            async with _pool(guard, config=BrowserPoolConfig()) as pool:
                html = await _visit(pool, world.public_url("/scripted"))

            assert PUBLIC_MARKER in html
            assert "/own.js" in world.public.paths()
            assert world.internal.hits == []


class TestWhereTheGuardDoesNotApply:
    async def test_a_context_that_opted_into_private_networks_connects_directly(self) -> None:
        guard = EgressGuard(table_resolver)
        with attack_world() as world:
            async with _pool(guard) as pool:
                strict, strict_key = await pool.acquire_page(ContextType.CRAWL, context_key="strict")
                local, local_key = await pool.acquire_page(
                    ContextType.CRAWL, context_key="local", context_kwargs={"allow_private_networks": True}
                )
                try:
                    assert _REFUSED_BY_GUARD in await _goto_error(strict, f"{world.internal_literal}/secret")
                    assert await _goto_error(local, f"{world.internal_literal}/secret") == ""
                    assert INTERNAL_MARKER in await local.content()
                finally:
                    await pool.release_page(strict, strict_key)
                    await pool.release_page(local, local_key)

            assert world.internal.paths() == ["/secret"]  # only the context that opted in

    async def test_a_pool_without_a_guard_is_not_touched_by_any_of_it(self) -> None:
        with attack_world() as world:
            async with _pool(None) as pool:
                page, context_key = await pool.acquire_page(ContextType.CRAWL)
                try:
                    assert await _goto_error(page, f"{world.internal_literal}/secret") == ""
                finally:
                    await pool.release_page(page, context_key)


class TestTheGuardIsTheOnlyWayOut:
    async def test_after_the_guard_stops_a_connection_fails_as_a_proxy_error(self) -> None:
        guard = EgressGuard(table_resolver)
        with attack_world() as world:
            async with _pool(guard) as pool:
                page, context_key = await pool.acquire_page(ContextType.CRAWL)
                try:
                    assert await _goto_error(page, world.public_url("/plain")) == ""
                    await guard.stop()
                    assert _GUARD_GONE in await _goto_error(page, world.public_url("/own.js"))
                finally:
                    await pool.release_page(page, context_key)

            assert "/own.js" not in world.public.paths()

    async def test_shutting_the_pool_down_stops_the_guard(self) -> None:
        guard = EgressGuard(table_resolver)
        with attack_world() as world:
            async with _pool(guard) as pool:
                await _visit(pool, world.public_url("/plain"))
                settings = await guard.start()
            port = int(settings["server"].rsplit(":", 1)[1])

            assert guard.active == 0
            with pytest.raises(ConnectionRefusedError):
                await asyncio.open_connection("127.0.0.1", port)
            with pytest.raises(EgressGuardError, match="stopped"):
                await guard.start()


class TestWhatTheGuardLetsThrough:
    async def test_a_websocket_to_a_public_host_works_through_the_guard(self) -> None:
        """The refused WebSocket is part of the attack page; this is the permitted one, an echo server behind a public name."""
        websockets = pytest.importorskip("websockets.asyncio.server")

        async def echo(connection: object) -> None:
            async for message in connection:  # type: ignore[attr-defined]
                await connection.send(message)  # type: ignore[attr-defined]

        guard = EgressGuard(table_resolver)
        async with websockets.serve(echo, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with attack_world() as world:
                async with _pool(guard) as pool:
                    page, context_key = await pool.acquire_page(ContextType.CRAWL)
                    try:
                        await page.goto(world.public_url("/plain"))
                        echoed = await page.evaluate(
                            f"""new Promise((resolve, reject) => {{
                                const socket = new WebSocket("ws://{PUBLIC_HOST}:{port}/");
                                socket.onopen = () => socket.send("ping");
                                socket.onmessage = (event) => resolve(event.data);
                                socket.onerror = () => reject(new Error("the socket failed"));
                            }})"""
                        )
                    finally:
                        await pool.release_page(page, context_key)

        assert echoed == "ping"


class _IgnoresContextProxy:
    """A browser whose contexts ignore the proxy option: what the guard's canary exists to catch."""

    def __init__(self, browser: Browser) -> None:
        self._browser = browser

    async def new_context(self, **options: object) -> BrowserContext:
        options.pop("proxy", None)
        return await self._browser.new_context(**options)  # type: ignore[arg-type]


class TestTheCanary:
    async def test_a_browser_that_routes_through_the_guard_passes_it(self) -> None:
        guard = EgressGuard(table_resolver)
        async with _pool(None) as pool:
            await pool.warmup(browsers=1, pages_per_context=0)
            browser = pool._browsers[0].browser

            await guard.verify_routing(browser)

            assert guard.handled >= 1
        await guard.stop()

    async def test_a_browser_that_does_not_is_refused(self) -> None:
        guard = EgressGuard(table_resolver)
        async with _pool(None) as pool:
            await pool.warmup(browsers=1, pages_per_context=0)
            browser = pool._browsers[0].browser

            with pytest.raises(EgressGuardError, match="did not route"):
                await guard.verify_routing(_IgnoresContextProxy(browser))  # type: ignore[arg-type]
        await guard.stop()


class TestWebRtc:
    """WebRTC sends UDP straight from the browser, around any proxy; the pool's launch flag forbids it."""

    @staticmethod
    async def _stun_datagrams(*, with_flag: bool) -> int:
        listener = UdpListener()
        guard = EgressGuard(table_resolver)
        try:
            with attack_world() as world:
                async with _pool(guard) as pool:
                    if not with_flag:
                        args = pool._launch_options["args"]
                        assert isinstance(args, list)
                        args[:] = [arg for arg in args if arg != _WEBRTC_FLAG]
                    page, context_key = await pool.acquire_page(ContextType.CRAWL)
                    try:
                        await page.goto(world.public_url("/plain"))
                        await page.evaluate(listener.stun_probe())
                    finally:
                        await pool.release_page(page, context_key)
            await asyncio.sleep(0.4)
            return listener.datagrams
        finally:
            listener.close()

    async def test_without_the_flag_the_browser_sends_udp_around_the_guard(self) -> None:
        assert await self._stun_datagrams(with_flag=False) > 0

    async def test_with_the_flag_no_datagram_leaves_the_browser(self) -> None:
        assert await self._stun_datagrams(with_flag=True) == 0
