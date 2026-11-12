"""Real-Chromium harness for the browser extension: the unpacked extension, the production bridge routes, fixture sites.

[INPUT]
- patchright.async_api::async_playwright (POS: starts a real Chromium profile that loads the unpacked extension)
- aiohttp.web (POS: serves the cookie-gated fixture sites)
- uvicorn (POS: serves the production extension routes inside the test's event loop, so the extension reaches the bridge
  through a real WebSocket and the bridge's Playwright calls share the loop that owns the relay)
- app.api.extension.router::router, ws_router (POS: the production REST and WebSocket routes of the bridge)
- app.services.extension.bridge::ExtensionBridgeService, get_extension_bridge (POS: the production bridge under test)
- app.services.extension.cdp_relay.manager (POS: process-wide relay singleton, reset around every stack)

[OUTPUT]
- FixtureSite: loopback site that answers under several host names and gates its pages on a login cookie
- BridgeServer: the production extension routes on an ephemeral loopback port
- ExtensionBrowser: the user's daily browser with the extension loaded; popup-style messaging, extension-page scripts,
  service-worker termination
- RealExtensionStack / real_extension_stack: all three wired together and connected; user sign-in, the Agent's
  Playwright browser (the bridge's own connect(), through the CDP relay) and the Agent's BrowserSession on top of the
  production browser pool
- new_agent_page: a context and a blank page the way the Agent's browser pool opens them
- wait_until: bounded polling for asynchronous conditions

[POS]
Shared by the real-browser extension e2e tests. Nothing here is mocked: the same extension files a user installs run in a
real Chromium, talk to the same routes and bridge the server mounts, and read pages from a site that needs a login cookie.
The browser resolves the fixture host names to loopback itself, so no system resolver or hosts file is touched.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from aiohttp import web
from fastapi import FastAPI
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.session import BrowserSession
from patchright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.api.extension.router import router as extension_router
from app.api.extension.router import ws_router as extension_ws_router
from app.config.settings import settings
from app.services.extension.bridge import ExtensionBridgeService, get_extension_bridge
from app.services.extension.bridge import factory as bridge_factory
from app.services.extension.cdp_relay import manager as relay_manager

EXTENSION_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-extension"
INTRANET_HOST = "intranet.example"
OTHER_HOST = "other.example"
_FIXTURE_HOSTS = (INTRANET_HOST, OTHER_HOST)
_PAGE = "<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{body}</body></html>"


async def wait_until(condition: Callable[[], Awaitable[bool]], what: str, *, timeout: float = 20.0) -> None:
    """Poll ``condition`` until it holds; the failure names what never happened."""
    deadline = time.monotonic() + timeout
    while not await condition():
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out after {timeout:.0f}s waiting for: {what}")
        await asyncio.sleep(0.1)


class FixtureSite:
    """Loopback site reachable under every fixture host name; its pages need the cookie ``/login`` hands out."""

    def __init__(self) -> None:
        self.port = 0
        self._runner: web.AppRunner | None = None

    @property
    def host_resolver_rules(self) -> str:
        """Chromium flag value that maps every fixture host to loopback inside the browser only."""
        return ",".join(f"MAP {host} 127.0.0.1" for host in _FIXTURE_HOSTS)

    def url(self, host: str, path: str = "/") -> str:
        return f"http://{host}:{self.port}{path}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/login", self._login)
        app.router.add_get("/secret", self._secret)
        app.router.add_get("/orders", self._orders)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", 0).start()
        self.port = self._runner.addresses[0][1]

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    @staticmethod
    def _host(request: web.Request) -> str:
        return request.host.split(":")[0]

    @staticmethod
    def _html(title: str, body: str, *, status: int = 200) -> web.Response:
        return web.Response(text=_PAGE.format(title=title, body=body), content_type="text/html", status=status)

    async def _login(self, request: web.Request) -> web.Response:
        response = self._html("Signed in", f"<p id='who'>{request.query.get('user', 'alice')} on {self._host(request)}</p>")
        response.set_cookie("sid", request.query.get("user", "alice"), httponly=True, path="/")
        return response

    async def _secret(self, request: web.Request) -> web.Response:
        user = request.cookies.get("sid")
        if not user:
            return self._html("Login required", "<p id='denied'>login required</p>", status=401)
        body = f"<h1 id='who'>{user}</h1><p id='data'>private-data-42</p><a id='orders-link' href='/orders'>Orders</a>"
        return self._html("Secret", body)

    async def _orders(self, request: web.Request) -> web.Response:
        if not request.cookies.get("sid"):
            return self._html("Login required", "<p id='denied'>login required</p>", status=401)
        body = "<p id='orders'>Order 1001</p><button id='confirm' onclick=\"document.title='confirmed'\">Confirm</button>"
        return self._html("Orders", body)


class BridgeServer:
    """The production extension routes on an ephemeral loopback port, inside the test's event loop."""

    def __init__(self) -> None:
        self.port = 0
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}{settings.api_prefix}/ws/extension"

    @property
    def http_base(self) -> str:
        return f"http://127.0.0.1:{self.port}{settings.api_prefix}"

    async def start(self) -> None:
        app = FastAPI()
        app.include_router(extension_router, prefix=settings.api_prefix)
        app.include_router(extension_ws_router, prefix=f"{settings.api_prefix}/ws")
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off", timeout_graceful_shutdown=2)
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())

        async def started() -> bool:
            assert self._task is not None
            if self._task.done():
                self._task.result()
                raise AssertionError("Bridge server stopped before it started")
            return self._server is not None and self._server.started

        await wait_until(started, "the bridge server to listen", timeout=15.0)
        assert self._server is not None
        self.port = self._server.servers[0].sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None and self._task is not None:
            self._server.should_exit = True
            await asyncio.wait_for(self._task, timeout=15.0)
        self._server = self._task = None


class ExtensionBrowser:
    """The user's daily browser: a real Chromium profile with the unpacked extension loaded."""

    def __init__(self, context: BrowserContext, extension_id: str) -> None:
        self.context = context
        self.extension_id = extension_id
        self._driver: Page | None = None

    @property
    def version(self) -> str:
        return str(json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))["version"])

    async def popup(self) -> Page:
        """The extension's popup page; also the page messages reach the service worker from."""
        if self._driver is None or self._driver.is_closed():
            self._driver = await self.context.new_page()
            await self._driver.goto(f"chrome-extension://{self.extension_id}/src/popup.html")
        return self._driver

    async def send(self, message: dict[str, object]) -> dict[str, object]:
        """Deliver a message to the service worker exactly as the popup and the side panel do."""
        page = await self.popup()
        reply = await page.evaluate("(message) => chrome.runtime.sendMessage(message)", message, isolated_context=False)
        assert isinstance(reply, dict), f"Extension answered {reply!r} to {message!r}"
        return reply

    async def evaluate(self, function: str, argument: object = None) -> object:
        """Run a JavaScript function on an extension page, where every extension API the manifest grants is available."""
        page = await self.popup()
        return await page.evaluate(function, argument, isolated_context=False)

    async def stop_service_worker(self) -> None:
        """Terminate the extension's service worker the way the browser does when it reclaims an idle one.

        The next message or alarm starts a fresh worker with none of the previous worker's memory.
        """
        holder = await self.context.new_page()
        try:
            session = await self.context.new_cdp_session(holder)
            versions: list[dict[str, object]] = []
            session.on("ServiceWorker.workerVersionUpdated", lambda event: versions.extend(event.get("versions", [])))
            await session.send("ServiceWorker.enable")

            async def worker_known() -> bool:
                return any(self.extension_id in str(version.get("scriptURL")) for version in versions)

            await wait_until(worker_known, "the extension's service worker to be reported")
            for version in versions:
                if self.extension_id in str(version.get("scriptURL")):
                    await session.send("ServiceWorker.stopWorker", {"versionId": version["versionId"]})
        finally:
            await holder.close()

    async def connect_through_popup(self, ws_url: str) -> None:
        """Type the server address into the popup and press Connect, as a user would."""
        page = await self.popup()
        await page.fill("#server-url", ws_url)
        await page.click("#btn-connect")

    async def open_user_tab(self, url: str) -> Page:
        """Open a page the way the user browses: nothing about it involves the extension or the Agent."""
        page = await self.context.new_page()
        await page.goto(url, wait_until="load")
        return page

    def user_tab_urls(self) -> list[str]:
        """URLs of every tab that is not an extension page."""
        return [page.url for page in self.context.pages if not page.url.startswith("chrome-extension://")]


@dataclass
class RealExtensionStack:
    """A connected extension, its bridge, the bridge's HTTP endpoints and the sites the user is logged in to."""

    site: FixtureSite
    server: BridgeServer
    browser: ExtensionBrowser
    bridge: ExtensionBridgeService
    playwright: Playwright

    async def authorize(self, domains: list[str]) -> None:
        """Set the authorized domains from the server side, as the settings page does."""
        await self.bridge.set_authorized_domains(domains)

        async def pushed() -> bool:
            reply = await self.browser.send({"type": "get_access_policy"})
            return reply.get("authorizedDomains") == domains

        await wait_until(pushed, f"the extension to receive authorized domains {domains}")

    async def log_in(self, host: str) -> Page:
        """The user signs in to a site in a tab of their own, as they would before asking the Agent for help."""
        return await self.browser.open_user_tab(self.site.url(host, "/login?user=alice"))

    @asynccontextmanager
    async def agent_browser(self) -> AsyncIterator[Browser]:
        """A Playwright browser the way the Agent gets one: through the production bridge and its CDP relay."""
        instance = await self.bridge.connect()
        try:
            yield instance.browser
        finally:
            await instance.browser.close()

    @asynccontextmanager
    async def agent_session(self) -> AsyncIterator[BrowserSession]:
        """The Agent's browser session as the tool setup builds it for the user's own browser (local mode, extension source)."""
        pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal(), extension_bridge=self.bridge)
        session = BrowserSession(
            pool,
            ContextType.AGENT,
            context_key="e2e-agent",
            extension_bridge=self.bridge,
            allow_private_networks=True,
            launch_mode_preference="extension",
        )
        try:
            yield session
        finally:
            await session.close()
            await pool.shutdown()

    async def handshaken(self) -> bool:
        """True while the extension is connected and its hello has been processed."""
        status = await self.bridge.get_status()
        return status.connected and status.handshake_ready


async def new_agent_page(browser: Browser) -> Page:
    """What the Agent's browser pool does for every task: a context of its own and a blank page in it."""
    context = await browser.new_context()
    return await context.new_page()


def find_page(browser: Browser, url_part: str) -> Page:
    """The page whose URL contains `url_part`, in any context: Playwright does not keep the default context first."""
    return next(page for context in browser.contexts for page in context.pages if url_part in page.url)


def _reset_bridge_singletons() -> None:
    bridge_factory._bridge_instance = None
    relay_manager._manager = None


@asynccontextmanager
async def real_extension_stack(profile_dir: Path) -> AsyncIterator[RealExtensionStack]:
    """Start the fixture site, the bridge routes and a Chromium profile whose extension is connected to them."""
    async with async_playwright() as playwright, AsyncExitStack() as cleanup:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Chromium is not installed for patchright")
        _reset_bridge_singletons()
        cleanup.callback(_reset_bridge_singletons)
        site, server = FixtureSite(), BridgeServer()
        await site.start()
        cleanup.push_async_callback(site.stop)
        await server.start()
        cleanup.push_async_callback(server.stop)
        bridge = get_extension_bridge()
        cleanup.push_async_callback(relay_manager.get_cdp_relay_manager().shutdown)
        cleanup.push_async_callback(bridge.disconnect)

        extension = str(EXTENSION_DIR)
        context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chromium",
            headless=True,
            ignore_default_args=["--disable-extensions"],
            args=[
                f"--disable-extensions-except={extension}",
                f"--load-extension={extension}",
                f"--host-resolver-rules={site.host_resolver_rules}",
            ],
        )
        cleanup.push_async_callback(context.close)
        worker = context.service_workers[0] if context.service_workers else await context.wait_for_event("serviceworker")
        browser = ExtensionBrowser(context, worker.url.split("/")[2])
        await browser.connect_through_popup(server.ws_url)
        stack = RealExtensionStack(site, server, browser, bridge, playwright)
        await wait_until(stack.handshaken, "the extension to connect and complete the handshake")
        yield stack
