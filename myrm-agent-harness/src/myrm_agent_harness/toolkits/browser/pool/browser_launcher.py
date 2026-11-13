"""Browser instance launcher with CDP connect and intelligent retry.


[INPUT]
- patchright.async_api::Playwright (POS: Patchright launcher)
- patchright.async_api::Browser (POS: Patchright browser instance)
- .config::LaunchMode, _DEFAULT_CDP_ENDPOINT (POS: launch method enum and default CDP endpoint)
- .chrome_discovery::discover_chrome_cdp_endpoint (POS: DevToolsActivePort-based browser discovery)
- .camoufox_availability::require_camoufox_ready (POS: non-downloading Camoufox readiness gate)
- .camoufox_launch::launch_camoufox (POS: Camoufox start with a persisted fingerprint)
- .browser_launch_env::chromium_launch_env (POS: environment of launched Chromium processes)
- .chromium_install::auto_install_chromium, build_install_failure_message (POS: zero-config Chromium installation)
- ..utils.page_health::is_driver_closed_error (POS: tells a call that failed on an exited Playwright driver from other failures)

[OUTPUT]
- BrowserLauncher: browser instance launcher (supports launch/connect/auto modes)
- BrowserInstance: browser instance metadata container (includes is_managed, last_active_at, _disconnected, expected_close)

[POS]
Dedicated to browser instance launching, including:
1. Playwright startup and management
2. New browser launch (chromium.launch)
3. CDP connection to existing Chrome (chromium.connect_over_cdp)
4. Automatic CDP port detection (HTTP GET /json/version)
5. Auto mode: DevToolsActivePort discovery → probe → connect → fallback to launch
6. Smart retry strategy (3 retries + exponential backoff)
7. Zero-config auto-install: a launch that reports a missing Chromium runs ``chromium_install`` and retries
8. Camoufox: started through `camoufox_launch` (fingerprint persistence, corrupted-JSON self-heal) behind a readiness gate that refuses to start without the browser build, so no implicit ~1.2 GB download runs inside a request
9. Driver recovery: a launch or CDP connect that fails because the Playwright driver process is gone drops the cached driver, so the next attempt starts a new one instead of failing on the dead one forever
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..exceptions import BrowserLaunchError
from ..utils.page_health import is_driver_closed_error
from .browser_launch_env import chromium_launch_env
from .camoufox_availability import require_camoufox_ready
from .camoufox_launch import launch_camoufox
from .chromium_install import auto_install_chromium, build_install_failure_message
from .config import _DEFAULT_CDP_ENDPOINT, BrowserEngine, LaunchMode

if TYPE_CHECKING:
    from patchright.async_api import Browser, BrowserContext, Playwright

    from .page_pool import PagePool

logger = logging.getLogger(__name__)


def _is_executable_missing(error: Exception) -> bool:
    """Detect if a launch failure is caused by missing browser executable."""
    msg = str(error).lower()
    return "executable doesn't exist" in msg or "no such file or directory" in msg


@dataclass
class BrowserInstance:
    """Browser instance metadata for pool scheduling and session preservation.

    is_managed: True when launched by BrowserLauncher; False when attached via CDP.
    _disconnected: Set on browser disconnect to avoid duplicate semaphore release.
    expected_close: Set before the pool or a session closes the browser on purpose (idle eviction,
        shutdown, engine switch), so the disconnect that follows is not read as a crash.
    """

    browser: Browser
    engine: str = "chromium_patchright"
    contexts: dict[str, BrowserContext] = field(default_factory=dict)
    page_pools: dict[str, PagePool] = field(default_factory=dict)
    load: int = 0
    last_active_at: float = field(default_factory=time.monotonic)
    _disconnected: bool = False
    is_managed: bool = True
    expected_close: bool = False


class BrowserLauncher:
    """Browser instance launcher with launch/connect/auto/remote/extension modes."""

    def __init__(
        self,
        launch_options: dict[str, object],
        launch_mode: LaunchMode = LaunchMode.LAUNCH,
        engine: BrowserEngine = BrowserEngine.CHROMIUM_PATCHRIGHT,
        cdp_endpoint: str | None = None,
        remote_ws_endpoint: str | None = None,
        remote_ws_headers: dict[str, str] | None = None,
        extension_bridge: object | None = None,
        fingerprint_dir: Path | None = None,
    ) -> None:
        self._launch_options = launch_options
        self._launch_mode = launch_mode
        self._engine = engine
        self._cdp_endpoint = cdp_endpoint or _DEFAULT_CDP_ENDPOINT
        self._remote_ws_endpoint = remote_ws_endpoint
        self._remote_ws_headers = remote_ws_headers
        self._extension_bridge = extension_bridge
        self._fingerprint_dir = fingerprint_dir
        self._playwright: Playwright | None = None
        self._total_browsers = 0

    async def _ensure_playwright(self) -> Playwright:
        if not self._playwright:
            from patchright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        return self._playwright

    async def _discard_playwright(self) -> None:
        """Stop and forget the cached driver, so the next ``_ensure_playwright`` starts a new one.

        The cache is cleared first: a caller that arrives while the old driver is still stopping must not pick it up.
        """
        playwright, self._playwright = self._playwright, None
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()

    async def _discard_playwright_if_gone(self, error: Exception) -> None:
        """Drop the cached driver when ``error`` says its process is gone.

        The driver took every browser it launched down with it, and a dead driver can neither launch nor
        connect anything: the next attempt has to run on a new one.
        """
        if self._playwright is not None and is_driver_closed_error(error):
            logger.warning("Playwright driver process is gone; the next attempt starts a new driver")
            await self._discard_playwright()

    async def create_browser(self, headers: dict[str, str] | None = None) -> BrowserInstance:
        """Create Browser via configured launch_mode (launch/connect/auto/remote/extension).

        AUTO mode: probe CDP → connect if available → fallback to launch.
        REMOTE mode: connect to remote WebSocket endpoint.
        EXTENSION mode: connect through browser extension's CDP proxy.

        Returns:
            BrowserInstance with initialized browser

        Raises:
            BrowserLaunchError: If all strategies fail

        """
        if self._launch_mode == LaunchMode.EXTENSION:
            return await self._connect_extension()

        if self._launch_mode == LaunchMode.REMOTE:
            if not self._remote_ws_endpoint:
                raise BrowserLaunchError("remote_ws_endpoint is required for REMOTE launch mode")
            merged_headers = dict(self._remote_ws_headers or {})
            if headers:
                merged_headers.update(headers)
            return await self._connect_existing(self._remote_ws_endpoint, headers=merged_headers)

        from .chrome_discovery import resolve_e2e_cdp_endpoint

        e2e_endpoint = resolve_e2e_cdp_endpoint()
        if e2e_endpoint:
            # E2E owns exactly this Chrome and it carries the profile the run was
            # provisioned with (auth session, extension bridge). Discovering another
            # browser here would silently retarget the run at a foreign profile, and
            # launching a fresh Chromium would do the same with an empty one — so both
            # are refused and the failure stays attributable to the E2E Chrome itself.
            if not await self._probe_cdp(e2e_endpoint):
                msg = (
                    f"E2E Chrome is not reachable via CDP at {e2e_endpoint}; refusing "
                    "local-browser discovery and fresh launch while MYRM_CHROME_E2E is "
                    "enabled. Ensure the chrome-e2e preflight started this Chrome."
                )
                logger.error(msg)
                raise BrowserLaunchError(msg)
            return await self._connect_existing(e2e_endpoint, headers=headers)

        if self._launch_mode in (LaunchMode.CONNECT, LaunchMode.AUTO):
            discovered = await self._discover_local_chrome()
            endpoint_to_try = discovered or self._cdp_endpoint
            if self._launch_mode == LaunchMode.CONNECT:
                return await self._connect_existing(endpoint_to_try, headers=headers)
            if await self._probe_cdp(endpoint_to_try):
                try:
                    inst = await self._connect_existing(endpoint_to_try, headers=headers)
                    logger.info(
                        "AUTO mode: connected to existing Chrome via CDP at %s%s",
                        endpoint_to_try,
                        " (discovered)" if discovered else "",
                    )
                    return inst
                except Exception as exc:
                    logger.warning("AUTO mode: CDP connect failed, falling back to launch: %s", exc)

        return await self._launch_new_browser()

    async def _discover_local_chrome(self) -> str | None:
        """Discover a locally running Chrome via DevToolsActivePort file scan.

        Runs the synchronous discovery in a thread executor to avoid blocking
        the event loop (filesystem I/O + TCP/HTTP probes).
        """
        from .chrome_discovery import discover_chrome_cdp_endpoint

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, discover_chrome_cdp_endpoint)

    async def _probe_cdp(self, endpoint: str) -> bool:
        """Probe CDP endpoint availability (HTTP /json/version or inspect WebSocket port)."""
        from .chrome_discovery import probe_cdp_endpoint

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, probe_cdp_endpoint, endpoint)

    async def _connect_existing(self, endpoint: str, headers: dict[str, str] | None = None) -> BrowserInstance:
        """Connect to an existing Chrome instance via CDP with retry.

        Retries up to 3 times with exponential backoff (1s, 2s) to handle
        transient CDP unavailability (e.g. Chrome still initializing). A retry
        whose failure was an exited Playwright driver runs on a new driver.

        The returned BrowserInstance has is_managed=False.
        Calling browser.close() on a CDP-connected browser only
        disconnects the CDP session — it does NOT kill the Chrome process.
        """
        last_exc: Exception | None = None

        from .chrome_prompt_guard import watch_chrome_remote_debugging_prompt

        for attempt in range(3):
            pw = await self._ensure_playwright()
            try:
                async with watch_chrome_remote_debugging_prompt(timeout=4.0):
                    # The driver rejects an empty mapping ("headers: expected array, got object"): none means None.
                    browser = await pw.chromium.connect_over_cdp(endpoint, headers=headers or None)
                self._total_browsers += 1
                logger.info(
                    f"Connected to existing Chrome via CDP at {endpoint} "
                    f"(total: {self._total_browsers}, contexts: {len(browser.contexts)})"
                )
                return BrowserInstance(browser=browser, engine=self._engine.value, is_managed=False)

            except Exception as exc:
                last_exc = exc
                logger.warning(f"CDP connect failed (attempt {attempt + 1}/3): {exc}")
                await self._discard_playwright_if_gone(exc)
                if attempt < 2:
                    await asyncio.sleep(2**attempt)

        error_msg = f"Failed to connect to Chrome via CDP at {endpoint} after 3 attempts: {last_exc}"
        logger.error(error_msg)
        raise BrowserLaunchError(error_msg) from last_exc

    async def _launch_new_browser(self) -> BrowserInstance:
        """Launch new browser with intelligent retry (3 attempts + exponential backoff).

        When the Chromium executable is missing (common for first-time Tauri desktop
        users), automatically installs it via ``patchright install chromium`` and retries.
        A cooldown prevents repeated install attempts after failure.
        """
        last_exc: Exception | None = None
        auto_installed = False
        # Patchright's TimeoutError is distinct from builtins.TimeoutError; both
        # must be recognized so launch timeouts get the retry-with-backoff path.
        from ..utils import is_timeout_error

        if self._engine == BrowserEngine.FIREFOX_CAMOUFOX:
            # Outside the retry loop: a missing build is not transient, and the
            # library would otherwise download it implicitly mid-request.
            require_camoufox_ready()

        for attempt in range(3):
            try:
                if self._engine == BrowserEngine.FIREFOX_CAMOUFOX:
                    browser = await launch_camoufox(self._launch_options, self._fingerprint_dir)

                    logger.info(f"Launched new Camoufox Browser instance (attempt {attempt + 1}/3)")
                else:
                    pw = await self._ensure_playwright()
                    launch_kwargs = dict(self._launch_options)
                    launch_kwargs["env"] = chromium_launch_env()
                    if sys.platform == "darwin":
                        raw_args = launch_kwargs.get("args")
                        existing_args = list(raw_args) if isinstance(raw_args, list | tuple) else []
                        if not any("MacAppCodeSignClone" in str(arg) for arg in existing_args):
                            existing_args.append("--disable-features=MacAppCodeSignClone")
                            launch_kwargs["args"] = existing_args
                    browser = await pw.chromium.launch(**launch_kwargs)  # type: ignore[arg-type]

                    logger.info(f"Launched new Patchright Chromium instance (attempt {attempt + 1}/3)")

                self._total_browsers += 1
                return BrowserInstance(browser=browser, engine=self._engine.value, is_managed=True)

            except Exception as exc:
                await self._discard_playwright_if_gone(exc)

                if is_timeout_error(exc):
                    last_exc = exc
                    logger.warning(f"Browser launch timeout (attempt {attempt + 1}/3): {exc}")
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                    continue

                if isinstance(exc, ConnectionError):
                    last_exc = exc
                    logger.warning(f"Browser launch connection error (attempt {attempt + 1}/3): {exc}")
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                    continue

                last_exc = exc
                logger.warning(f"Browser launch failed (attempt {attempt + 1}/3): {exc}")

                if (
                    not auto_installed
                    and _is_executable_missing(exc)
                    and self._engine != BrowserEngine.FIREFOX_CAMOUFOX
                ):
                    logger.info("Chromium executable not found — attempting auto-install")
                    if await auto_install_chromium():
                        auto_installed = True
                        # Reset playwright so the new executable is picked up
                        await self._discard_playwright()
                        continue  # retry immediately after install

                if attempt < 2:
                    await asyncio.sleep(2**attempt)

        error_msg = f"Failed to create Browser after 3 attempts: {last_exc}"
        if self._engine == BrowserEngine.FIREFOX_CAMOUFOX:
            error_msg = f"Camoufox stealth engine failed to launch after 3 attempts: {last_exc}"
        elif last_exc and _is_executable_missing(last_exc):
            error_msg = build_install_failure_message(last_exc)
        logger.error(error_msg)
        raise BrowserLaunchError(error_msg) from last_exc

    async def _connect_extension(self) -> BrowserInstance:
        """Connect through browser extension's CDP proxy.

        The extension_bridge (injected from business layer) handles:
        - WebSocket connection management
        - Tab selection and domain authorization
        - chrome.debugger attachment and CDP message routing

        Returns:
            BrowserInstance with is_managed=False (extension owns the browser lifecycle).

        Raises:
            BrowserLaunchError: If extension bridge is not available or connection fails.
        """
        from .extension_bridge import ExtensionBridge, ExtensionBridgeNotAvailableError

        if self._extension_bridge is None:
            raise BrowserLaunchError(
                "extension_bridge is required for EXTENSION launch mode. "
                "Ensure the browser extension is installed and connected."
            )

        if not isinstance(self._extension_bridge, ExtensionBridge):
            raise BrowserLaunchError(
                f"extension_bridge must implement ExtensionBridge Protocol, got {type(self._extension_bridge).__name__}"
            )

        try:
            instance = await self._extension_bridge.connect(timeout=10.0)
            self._total_browsers += 1
            logger.info("EXTENSION mode: connected to user's browser via extension bridge")
            return instance
        except ExtensionBridgeNotAvailableError as exc:
            raise BrowserLaunchError(str(exc)) from exc
        except Exception as exc:
            raise BrowserLaunchError(f"Extension bridge connection failed: {exc}") from exc

    async def shutdown(self) -> None:
        """Shutdown Playwright."""
        await self._discard_playwright()
