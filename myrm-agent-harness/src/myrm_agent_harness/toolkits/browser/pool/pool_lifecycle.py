"""Lifecycle of the global pool: the background health and eviction loop, closing a browser, shutdown and hot reload.

[INPUT]
- .browser_launcher::BrowserInstance, BrowserLauncher (POS: browser instance metadata and its launcher)
- .config::BrowserEngine, BrowserPoolConfig, LaunchMode (POS: pool configuration)
- .context_factory::ContextFactory (POS: rebuilt when the proxy pool is replaced)
- .driver_leftovers::terminate_driver_browsers (POS: ends the browsers a dead driver left running)
- .proxy::ProxyPool (POS: proxy pool that can be replaced while the pool runs)
- ..utils.page_health::is_driver_closed_error (POS: tells a close that failed on an exited Playwright driver from other failures)

[OUTPUT]
- PoolLifecycleMixin: lifecycle loop, `_close_browser_instance`, `shutdown`, `update_proxy_pool`, `update_remote_endpoint` for GlobalBrowserPool

[POS]
Everything that starts, ends or reconfigures the pool as a whole. The loop runs the crash watchdog's tick every 30 s
and stops on its own when the pool is empty; closing an instance closes its page pools and contexts first and the
browser itself only when the pool launched it (a user's browser is never closed on the user's behalf). A launched
browser whose driver has exited cannot be closed that way, so its processes are ended instead.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from typing import TYPE_CHECKING

from ..utils.page_health import is_driver_closed_error
from .browser_launcher import BrowserInstance, BrowserLauncher
from .config import BrowserEngine, BrowserPoolConfig, LaunchMode
from .context_factory import ContextFactory
from .driver_leftovers import terminate_driver_browsers

if TYPE_CHECKING:
    from .proxy import ProxyPool

logger = logging.getLogger(__name__)


class PoolLifecycleMixin:
    """Background loop, close, shutdown and hot reload for GlobalBrowserPool.

    Requires host class to have:
    - _browsers: list[BrowserInstance]
    - _lock: asyncio.Lock
    - _config: BrowserPoolConfig
    - _launchers / _launch_options: launcher cache and launch options
    - _proxy_pool: ProxyPool | None
    - _context_factory: ContextFactory
    - _lifecycle_task: asyncio.Task[None] | None
    - _total_acquires / _total_releases: counters reported at shutdown
    """

    _browsers: list[BrowserInstance]
    _lock: asyncio.Lock
    _config: BrowserPoolConfig
    _launchers: dict[tuple[BrowserEngine, LaunchMode], BrowserLauncher]
    _launch_options: dict[str, object]
    _proxy_pool: ProxyPool | None
    _context_factory: ContextFactory
    _lifecycle_task: asyncio.Task[None] | None
    _total_acquires: int
    _total_releases: int

    if TYPE_CHECKING:

        async def _lifecycle_tick(self) -> None: ...

    def _ensure_lifecycle_loop(self) -> None:
        """Start the lifecycle background loop if not already running."""
        if self._lifecycle_task is not None and not self._lifecycle_task.done():
            return
        self._lifecycle_task = asyncio.create_task(self._lifecycle_loop())

    async def _lifecycle_loop(self) -> None:
        """Background loop: health-check crashed browsers and evict idle ones.

        Runs every 30 seconds. Exits automatically when the pool is empty.
        Health checks are performed outside the lock to avoid blocking acquire/release.
        """
        _lifecycle_interval_seconds = 30

        while True:
            await asyncio.sleep(_lifecycle_interval_seconds)

            if not self._browsers:
                logger.debug("Lifecycle loop: pool empty, stopping")
                return

            try:
                await self._lifecycle_tick()
                if self._proxy_pool:
                    self._proxy_pool.cleanup_expired_sessions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Lifecycle loop: unexpected error in tick, will retry next cycle")

    async def _close_browser_instance(self, browser_inst: BrowserInstance) -> None:
        """Close a specific browser instance and its contexts.

        A close that fails or times out is only logged: the toolkit holds no browser PID to signal, and a
        process that outlives its launcher is a leftover for Browser Doctor. The exception is a close that fails
        because the driver that launched the browser has exited: nothing can close that browser any more, so the
        browsers of that driver are ended through its token (``driver_leftovers``).
        """
        for _ctx_key, pool in browser_inst.page_pools.items():
            with contextlib.suppress(Exception):
                await pool.shutdown()

        for _ctx_key, context in browser_inst.contexts.items():
            with contextlib.suppress(Exception):
                await context.close()

        if browser_inst.is_managed:
            browser_inst.expected_close = True  # the disconnect this triggers is ours, not a crash
            try:
                # Try graceful close first with a timeout
                await asyncio.wait_for(browser_inst.browser.close(), timeout=5.0)
            except Exception as e:
                logger.warning(f"Graceful browser close failed or timed out: {e}")
                if browser_inst.driver_token is not None and is_driver_closed_error(e):
                    await terminate_driver_browsers(browser_inst.driver_token)

    async def shutdown(self) -> None:
        """Close all resources (called at app shutdown)."""
        logger.info(
            f"GlobalBrowserPool shutdown — stats: acquires={self._total_acquires}, "
            f"releases={self._total_releases}, browsers={len(self._browsers)}",
        )

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._lifecycle_task
            self._lifecycle_task = None

        async with self._lock:
            for browser_inst in self._browsers:
                # Use our new robust close method instead of direct close
                await self._close_browser_instance(browser_inst)

            self._browsers.clear()

            for launcher in self._launchers.values():
                await launcher.shutdown()
            self._launchers.clear()

        logger.info("GlobalBrowserPool shutdown completed")

    async def update_proxy_pool(self, proxy_pool: ProxyPool | None) -> None:
        """Hot-reload proxy pool without restarting the browser pool.

        Replaces the internal proxy pool and updates ContextFactory so all
        subsequent ``acquire_page`` calls use the new proxy configuration.
        Also toggles DNS-over-HTTPS launch flag to match the new state.
        """
        async with self._lock:
            self._proxy_pool = proxy_pool
            self._context_factory = ContextFactory(
                proxy_pool=proxy_pool,
                default_emulation=self._config.default_emulation,
            )
            doh_flag = "--dns-over-https-templates=https://cloudflare-dns.com/dns-query"
            args = list(raw) if isinstance(raw := self._launch_options.get("args"), list) else []
            if proxy_pool and doh_flag not in args:
                args.append(doh_flag)
            elif not proxy_pool:
                args = [a for a in args if a != doh_flag]
            self._launch_options["args"] = args
        logger.info("Proxy pool updated: %s", "enabled" if proxy_pool else "disabled")

    async def update_remote_endpoint(self, ws_url: str | None, headers: dict[str, str] | None = None) -> None:
        """Hot-reload remote WebSocket endpoint without restarting the pool.

        Replaces the frozen config with a new instance and evicts any cached REMOTE launcher
        so the next acquire_page(..., launch_mode_preference=REMOTE) picks up the new endpoint.
        """
        async with self._lock:
            self._config = dataclasses.replace(self._config, remote_ws_endpoint=ws_url, remote_ws_headers=headers)
            stale_keys = [k for k in self._launchers if k[1] == LaunchMode.REMOTE]
            for key in stale_keys:
                launcher = self._launchers.pop(key)
                await launcher.shutdown()
        logger.info("Remote endpoint updated: %s", "configured" if ws_url else "cleared")
