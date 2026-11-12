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
- ExtensionBrowser: the user's daily browser with the extension loaded; popup-style messaging
- RealExtensionStack / real_extension_stack: all three wired together and connected
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
from patchright.async_api import BrowserContext, Page, Playwright, async_playwright

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

        async def handshaken() -> bool:
            status = await bridge.get_status()
            return status.connected and status.handshake_ready

        await wait_until(handshaken, "the extension to connect and complete the handshake")
        yield RealExtensionStack(site, server, browser, bridge, playwright)
