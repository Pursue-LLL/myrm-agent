"""Page acquisition path of the global pool: acquire a page, release it, destroy a context.

[INPUT]
- patchright.async_api::BrowserContext, Page (POS: Patchright context and page instances)
- .browser_launcher::BrowserInstance (POS: browser instance metadata)
- .config::BrowserEngine, BrowserPoolConfig, LaunchMode (POS: pool configuration and launch selectors)
- .context_factory::ContextFactory (POS: context creation factory)
- .extension_bridge::ExtensionBrowserInstance (POS: the user's own browser reached through the extension)
- .memory_guard::MemoryGuard (POS: memory pressure check before an acquisition)
- .page_acquisition::PageAcquisition (POS: cancel-safe claim on one permit and the page taken for it)
- .page_pool::PagePool (POS: page object pool)
- ..utils.page_health::is_driver_closed_error (POS: tells an acquisition that failed on an exited Playwright driver from other failures)

[OUTPUT]
- PoolAcquisitionMixin: `acquire_page`, `release_page` and `destroy_context` for GlobalBrowserPool

[POS]
Hands a page out and takes it back. An acquisition takes one global permit, schedules a browser, creates the context
and page pool on first use (outside the lock, inserted under it) and counts the page as in use. An acquisition that
fails because the Playwright driver exited is retried once, after the browsers the driver took down are evicted.
A release returns the permit unless a crash callback already did (semaphore safety net).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import TYPE_CHECKING

from ..utils.page_health import is_driver_closed_error
from .extension_bridge import ExtensionBrowserInstance
from .page_acquisition import PageAcquisition

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext, Page

    from .browser_launcher import BrowserInstance
    from .browser_pool import ContextType
    from .config import BrowserEngine, BrowserPoolConfig, LaunchMode
    from .context_factory import ContextFactory
    from .memory_guard import MemoryGuard
    from .page_pool import PagePool

logger = logging.getLogger(__name__)


class PoolAcquisitionMixin:
    """Acquire, release and destroy path for GlobalBrowserPool.

    Requires host class to have:
    - _browsers: list[BrowserInstance]
    - _lock: asyncio.Lock
    - _global_semaphore: asyncio.Semaphore
    - _config: BrowserPoolConfig (with engine and resource_block)
    - _memory_guard: MemoryGuard
    - _context_factory: ContextFactory
    - _crash_handled_pages: set[int]
    - _total_acquires / _total_releases / _current_pages_in_use: int
    - _make_page_pool, _get_least_loaded_browser, _register_page_crash_handler, _ensure_lifecycle_loop,
      _evict_after_driver_exit (provided by GlobalBrowserPool and its other mixins)
    """

    _browsers: list[BrowserInstance]
    _lock: asyncio.Lock
    _global_semaphore: asyncio.Semaphore
    _config: BrowserPoolConfig
    _memory_guard: MemoryGuard
    _context_factory: ContextFactory
    _crash_handled_pages: set[int]
    _total_acquires: int
    _total_releases: int
    _current_pages_in_use: int

    if TYPE_CHECKING:

        def _make_page_pool(
            self, browser_inst: BrowserInstance, context: BrowserContext, *, max_size: int = 10
        ) -> PagePool: ...

        async def _get_least_loaded_browser(
            self, engine: BrowserEngine, launch_mode: LaunchMode | None = None
        ) -> BrowserInstance: ...

        def _register_page_crash_handler(self, page: Page, inst: BrowserInstance) -> None: ...

        def _ensure_lifecycle_loop(self) -> None: ...

        async def _evict_after_driver_exit(self) -> None: ...

    async def acquire_page(
        self,
        context_type: ContextType,
        context_key: str | None = None,
        context_kwargs: dict[str, object] | None = None,
        engine_preference: BrowserEngine | None = None,
        launch_mode_preference: LaunchMode | None = None,
    ) -> tuple[Page, str]:
        """Smart page allocation (with global concurrency limit).

        Load-based smart scheduling, auto-creates or reuses Context/Page.
        Uses double-checked locking (DCL), holding lock only when modifying shared state.

        An acquisition that fails because the Playwright driver exited is retried once, after the browsers the
        driver took down are evicted: the retry runs on a new browser instead of the dead one.

        Args:
            context_type: Context type (CRAWL/AGENT/STEALTH)
            context_key: Context identifier (same key reuses Context, for session isolation)
            context_kwargs: Additional BrowserContext params (e.g. record_video_dir)
            engine_preference: Preferred browser engine. Falls back to config default if None.
            launch_mode_preference: Per-request launch mode override (e.g. EXTENSION for agents that need real browser sessions).

        Returns:
            (page, context_key) — Page instance and actual context_key used

        """
        acquire = functools.partial(
            self._acquire_page_once,
            context_type,
            context_key,
            context_kwargs,
            engine_preference,
            launch_mode_preference,
        )
        try:
            return await acquire()
        except Exception as error:
            if not is_driver_closed_error(error):
                raise
            logger.warning(f"Page acquisition failed on an exited Playwright driver, retrying once: {error}")
        await self._evict_after_driver_exit()
        return await acquire()

    async def _acquire_page_once(
        self,
        context_type: ContextType,
        context_key: str | None,
        context_kwargs: dict[str, object] | None,
        engine_preference: BrowserEngine | None,
        launch_mode_preference: LaunchMode | None,
    ) -> tuple[Page, str]:
        """One acquisition attempt: ``acquire_page`` without the retry after a driver exit."""
        engine = engine_preference or self._config.engine
        async with PageAcquisition(self._global_semaphore, self._crash_handled_pages) as claim:
            await self._memory_guard.check_memory()

            # 1. Under lock: read state, update counters
            async with self._lock:
                self._total_acquires += 1
                browser_inst = await self._get_least_loaded_browser(engine, launch_mode_preference)
                ctx_key = context_key or f"{context_type.value}_{id(self)}"
                needs_creation = ctx_key not in browser_inst.contexts

            # 2. Outside lock: create resources (DCL)
            if needs_creation:
                # Create Context (async I/O, no lock held)
                merged_kwargs = dict(context_kwargs) if context_kwargs else {}
                if "resource_block" not in merged_kwargs:
                    merged_kwargs["resource_block"] = self._config.resource_block

                new_context = await self._context_factory.create_context(
                    browser_inst.browser,
                    context_type.value,
                    extra_kwargs=merged_kwargs,
                    context_key=ctx_key,
                    extension_attached=isinstance(browser_inst, ExtensionBrowserInstance),
                )
                new_pool = self._make_page_pool(browser_inst, new_context)

                # Under lock: check and insert (prevent duplicate creation)
                async with self._lock:
                    if ctx_key not in browser_inst.contexts:
                        browser_inst.contexts[ctx_key] = new_context
                        browser_inst.page_pools[ctx_key] = new_pool
                    else:
                        # Clean up unused resources (prevent leaks)
                        needs_creation = False
                        try:
                            await new_context.close()
                            await new_pool.shutdown()
                        except Exception as e:
                            logger.warning(f"Failed to cleanup unused context: {e}")

            # 3. Outside lock: acquire Page (async I/O) + register crash handler (L2)
            pool = browser_inst.page_pools[ctx_key]
            page = await pool.acquire()
            claim.hold(pool, page)
            self._register_page_crash_handler(page, browser_inst)

            # 4. Under lock: update load count, concurrency count, active time
            async with self._lock:
                browser_inst.load += 1
                browser_inst.last_active_at = time.monotonic()
                self._current_pages_in_use += 1
                claim.commit()

            self._ensure_lifecycle_loop()
            return page, ctx_key

    async def destroy_context(self, context_key: str, *, only_if_idle: bool = False) -> bool:
        """Explicitly destroy a context and its associated page pool.

        Args:
            context_key: The identifier of the context to destroy
            only_if_idle: Return False and keep the context while another session still holds pages in it

        Returns:
            True when the context was destroyed.

        Raises:
            RuntimeError: Pages are still in use and ``only_if_idle`` is not set.
        """
        logger.info(f"Attempting to destroy context: {context_key}")
        async with self._lock:
            for browser_inst in self._browsers:
                if context_key in browser_inst.contexts:
                    pool = browser_inst.page_pools.get(context_key)

                    # Safety Guard: Ensure no pages are currently in use
                    if pool and pool.active_pages_count > 0:
                        if only_if_idle:
                            logger.info(f"Context {context_key} kept: {pool.active_pages_count} pages in use")
                            return False
                        logger.error(
                            f"Concurrency Guard Triggered: {pool.active_pages_count} pages still active in {context_key}"
                        )
                        raise RuntimeError(
                            f"Cannot destroy context {context_key}: "
                            f"{pool.active_pages_count} pages are still in use. "
                            f"Ensure all pages are released before destroying."
                        )

                    context = browser_inst.contexts.pop(context_key)
                    if pool:
                        browser_inst.page_pools.pop(context_key)

                    try:
                        if pool:
                            await pool.shutdown()
                        await context.close()
                        logger.info(f"Successfully destroyed context: {context_key}")
                    except Exception as e:
                        logger.warning(f"Error while destroying context {context_key}: {e}")
                    return True

            logger.warning(f"Context {context_key} not found for destruction")
            return False

    async def release_page(self, page: Page, context_key: str) -> None:
        """Release Page back to pool (free global concurrency slot).

        Semaphore safety net: if the page/browser was already handled by a crash callback,
        skip semaphore release to prevent over-release.

        Args:
            page: Page instance to release
            context_key: context_key returned by acquire

        """
        page_id = id(page)
        skip_semaphore = False

        try:
            async with self._lock:
                self._total_releases += 1

                if page_id in self._crash_handled_pages:
                    self._crash_handled_pages.discard(page_id)
                    skip_semaphore = True
                    return

                self._current_pages_in_use = max(0, self._current_pages_in_use - 1)

                found = False
                for browser_inst in self._browsers:
                    if context_key in browser_inst.page_pools:
                        if browser_inst._disconnected:
                            skip_semaphore = True
                        else:
                            await browser_inst.page_pools[context_key].release(page)
                            browser_inst.load = max(0, browser_inst.load - 1)
                            browser_inst.last_active_at = time.monotonic()
                        found = True
                        break

                if not found:
                    skip_semaphore = True

        finally:
            if not skip_semaphore:
                self._global_semaphore.release()
