"""Global browser pool with intelligent scheduling and multi-tenant isolation.

[INPUT]
- patchright.async_api::BrowserContext (POS: Patchright context instance)
- .browser_launcher::BrowserLauncher, BrowserInstance (POS: browser launcher and instance metadata)
- .context_factory::ContextFactory (POS: context creation factory)
- .egress_guard::EgressGuard (POS: loopback proxy that lets the contexts of launched browsers connect only to addresses the SSRF policy admits)
- .page_pool::PagePool (POS: page object pool)
- .config::BrowserPoolConfig (POS: browser pool config)
- .memory_guard::MemoryGuard (POS: memory pressure check)
- .proxy::ProxyPool (POS: proxy rotation and sticky sessions)
- .throttle::ThrottleStrategy, create_throttle_strategy (POS: throttle strategy)
- .circuit_breaker::CircuitBreaker (POS: circuit breaker)
- .extension_bridge::ExtensionBrowserInstance (POS: the user's own browser reached through the extension)
- .pool_acquisition::PoolAcquisitionMixin (POS: acquire a page, release it, destroy a context)
- .crash_watchdog::CrashWatchdogMixin (POS: three-layer crash recovery)
- .pool_scheduling::PoolSchedulingMixin (POS: launcher cache and least-loaded browser selection)
- .pool_lifecycle::PoolLifecycleMixin (POS: background loop, close, shutdown, hot reload)
- .pool_diagnostics::PoolDiagnosticsMixin (POS: statistics, health, page ownership)

[OUTPUT]
- ContextType: context purpose classification enum (CRAWL/AGENT/STEALTH)
- GlobalBrowserPool: global browser pool (smart scheduling, resource management, automatic crash recovery)

[POS]
Global browser resource pool. Manages Browser/Context/Page three-layer resources, implementing:
1. Zero-copy page reuse (delegates to PagePool)
2. Smart load scheduling (least-loaded first)
3. Type-based isolation (CRAWL/AGENT/STEALTH each with independent resource pools)
4. Elastic scaling (dynamically creates/destroys Browser instances)
5. Global concurrency limit (Semaphore controls total concurrency)
6. Lifecycle management (background loop: idle reclamation + crash detection)
7. Three-layer automatic crash recovery (L1: browser disconnect event, L2: page crash event, L3: lifecycle fallback);
   an acquisition that fails on an exited Playwright driver evicts the browsers it cut off and retries once
8. Semaphore safety net (prevents semaphore leaks or double releases on crash and on a cancelled or failed acquisition)
9. Connection-level network isolation: with an ``egress_guard`` the contexts of browsers the pool launched connect only through
   it, and the browser may not send UDP outside a proxy (WebRTC); see ``egress_guard.py``

This module owns the pool state, construction and warmup; the acquire/release/destroy path, scheduling, lifecycle and
monitoring are the mixins above.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from enum import Enum
from typing import TYPE_CHECKING

from .browser_launcher import BrowserInstance, BrowserLauncher
from .circuit_breaker import CircuitBreaker
from .config import BrowserEngine, BrowserPoolConfig, LaunchMode
from .context_factory import ContextFactory
from .crash_watchdog import CrashWatchdogMixin
from .extension_bridge import ExtensionBrowserInstance
from .memory_guard import MemoryGuard
from .page_pool import PagePool
from .pool_acquisition import PoolAcquisitionMixin
from .pool_diagnostics import PoolDiagnosticsMixin
from .pool_lifecycle import PoolLifecycleMixin
from .pool_scheduling import PoolSchedulingMixin
from .proxy import ProxyPool
from .throttle import ThrottleStrategy, create_throttle_strategy

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext

    from .egress_guard import EgressGuard
    from .extension_bridge import ExtensionBridge

logger = logging.getLogger(__name__)

_DEFAULT_LAUNCH_OPTIONS: dict[str, object] = {
    "headless": os.getenv("VISUAL_DESKTOP") != "1",
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-focus-on-load",
        "--disable-window-activation",
        "--disable-extensions",
        "--disable-gpu",
        "--disable-plugins",
    ],
}

if os.getenv("VISUAL_DESKTOP") == "1" and sys.platform != "darwin":
    _DEFAULT_LAUNCH_OPTIONS["env"] = {**os.environ, "DISPLAY": ":99"}

if sys.platform == "darwin":
    args_list = _DEFAULT_LAUNCH_OPTIONS.get("args")
    if isinstance(args_list, list) and "--disable-features=MacAppCodeSignClone" not in args_list:
        args_list.append("--disable-features=MacAppCodeSignClone")

_DOH_FLAG = "--dns-over-https-templates=https://cloudflare-dns.com/dns-query"
# The egress guard carries TCP only; without this flag a page can open UDP sockets (WebRTC, STUN) that no proxy sees.
_WEBRTC_UDP_FLAG = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"


def _add_launch_flags(options: dict[str, object], *flags: str) -> None:
    """Add the missing ``flags`` to the ``args`` of ``options``, on a new list: a list the caller passed is never changed."""
    raw = options.get("args")
    args = list(raw) if isinstance(raw, list) else []
    args.extend(flag for flag in flags if flag not in args)
    options["args"] = args


class ContextType(Enum):
    """Context purpose classification.

    Different purposes use different launch parameters and resource isolation strategies.
    """

    CRAWL = "crawl"
    AGENT = "agent"
    STEALTH = "stealth"


class GlobalBrowserPool(
    PoolAcquisitionMixin, PoolLifecycleMixin, PoolSchedulingMixin, PoolDiagnosticsMixin, CrashWatchdogMixin
):
    """Global browser pool — zero-copy, smart scheduling, type isolation, concurrency limits, lifecycle management.

    Singleton architecture, initialized at app startup, warmup and shutdown during FastAPI lifespan.

    Core features:
    1. Zero-copy reuse: PagePool rapidly resets pages via CDP commands
    2. Smart scheduling: least-load-first, dynamic scaling
    3. Type isolation: CRAWL/AGENT/STEALTH contexts with independent resource pools
    4. Elastic scaling: auto-creates new Browsers under high load, up to max_browsers
    5. Global concurrency limit: Semaphore controls total concurrent page count
    6. Lifecycle management: background loop auto-reclaims idle Browsers + detects and removes crashed instances
    """

    def __init__(
        self,
        max_browsers: int = 5,
        launch_options: dict[str, object] | None = None,
        proxy_pool: ProxyPool | None = None,
        config: BrowserPoolConfig | None = None,
        extension_bridge: ExtensionBridge | None = None,
        egress_guard: EgressGuard | None = None,
    ) -> None:
        """Initialize global browser pool.

        Args:
            max_browsers: Maximum Browser instance count
            launch_options: Patchright launch options (optional)
            proxy_pool: Proxy pool (supports rotation and sticky sessions)
            config: Browser pool configuration (concurrency/rate-limiting/circuit-breaker/resource interception)
            extension_bridge: ExtensionBridge protocol implementation for EXTENSION launch mode (injected from business layer)
            egress_guard: Connection guard for the contexts of browsers this pool launches (strict network policy);
                None leaves their connections to the browser. The pool stops it on shutdown.

        """
        self._browsers: list[BrowserInstance] = []
        self._max_browsers = max_browsers
        self._proxy_pool = proxy_pool
        self._lock = asyncio.Lock()
        self._total_acquires = 0
        self._total_releases = 0
        self._current_pages_in_use = 0

        self._crash_handled_pages: set[int] = set()
        self._crash_count_browser = 0
        self._crash_count_page = 0
        self._crash_tasks: set[asyncio.Task[None]] = set()

        self._config = config or BrowserPoolConfig()
        self._global_semaphore = asyncio.Semaphore(self._config.max_concurrent_pages)
        self._throttle_strategy = create_throttle_strategy(self._config.rate_limiter)
        self._memory_guard = MemoryGuard(self._config.memory_guard)

        cb_config = self._config.circuit_breaker
        self._circuit_breaker = (
            CircuitBreaker(
                failure_threshold=cb_config.failure_threshold,
                timeout=cb_config.timeout,
                callback=None,
            )
            if cb_config.enabled
            else None
        )

        # Dictionary of launchers keyed by (BrowserEngine, LaunchMode)
        self._launchers: dict[tuple[BrowserEngine, LaunchMode], BrowserLauncher] = {}
        self._launch_options = dict(launch_options or _DEFAULT_LAUNCH_OPTIONS)
        self._extension_bridge = extension_bridge
        self._egress_guard = egress_guard

        if self._proxy_pool:
            _add_launch_flags(self._launch_options, _DOH_FLAG)
        if egress_guard is not None:
            _add_launch_flags(self._launch_options, _WEBRTC_UDP_FLAG)

        self._context_factory = ContextFactory(
            proxy_pool=self._proxy_pool,
            default_emulation=self._config.default_emulation,
            egress_guard=egress_guard,
            ignore_https_errors=self._config.ignore_https_errors,
        )
        self._lifecycle_task: asyncio.Task[None] | None = None

        logger.info(
            f"GlobalBrowserPool initialized — max_concurrent_pages={self._config.max_concurrent_pages}, "
            f"mode={self._config.mode}, "
            f"launch_mode={self._config.launch_mode}, "
            f"throttle_mode={self._config.rate_limiter.mode}, "
            f"memory_guard={self._config.memory_guard.enabled}, "
            f"circuit_breaker={cb_config.enabled}, "
            f"idle_timeout={self._config.idle_timeout_seconds}s, "
            f"proxy_pool={'enabled' if self._proxy_pool else 'disabled'}, "
            f"egress_guard={'enabled' if egress_guard else 'disabled'}",
        )

    def _make_page_pool(
        self,
        browser_inst: BrowserInstance,
        context: BrowserContext,
        *,
        max_size: int = 10,
    ) -> PagePool:
        """Create a PagePool; external CDP browsers preserve profile session state.

        A page in the user's own browser (extension) is never kept idle: a tab the Agent let go of is closed
        instead of staying open in the user's window.
        """
        return PagePool(
            context,
            max_size=0 if isinstance(browser_inst, ExtensionBrowserInstance) else max_size,
            preserve_session=not browser_inst.is_managed,
        )

    def _guards_egress(self, browser_inst: BrowserInstance) -> bool:
        """Whether the contexts of this browser connect through the egress guard.

        Only a Chromium the pool launched itself can be pointed at it: a browser attached over CDP, a remote one and the
        user's own (extension) are not the pool's to configure, and Camoufox is another engine.
        """
        return (
            self._egress_guard is not None
            and browser_inst.is_managed
            and browser_inst.engine == BrowserEngine.CHROMIUM_PATCHRIGHT
        )

    async def warmup(self, browsers: int = 2, pages_per_context: int = 5) -> None:
        """Warm up pool (called at app startup).

        Creates the specified number of Browser instances and pre-creates Contexts and Pages for each ContextType.
        Warms up the default engine.

        Args:
            browsers: Number of Browsers to pre-create
            pages_per_context: Number of Pages to pre-create per Context

        """
        if browsers <= 0:
            logger.info("GlobalBrowserPool warmup skipped (browsers=%d)", browsers)
            return

        logger.info(f"GlobalBrowserPool warmup: browsers={browsers}, pages={pages_per_context}")

        launcher = self._get_launcher(self._config.engine)
        for _ in range(browsers):
            inst = await launcher.create_browser()
            self._register_disconnect_handler(inst)
            self._browsers.append(inst)

            for ctx_type in [ContextType.CRAWL, ContextType.AGENT]:
                ctx_key = f"{ctx_type.value}_warmup"
                inst.contexts[ctx_key] = await self._context_factory.create_context(
                    inst.browser,
                    ctx_type.value,
                    extension_attached=isinstance(inst, ExtensionBrowserInstance),
                    guard_egress=self._guards_egress(inst),
                )
                pool = self._make_page_pool(
                    inst,
                    inst.contexts[ctx_key],
                    max_size=pages_per_context * 2,
                )
                inst.page_pools[ctx_key] = pool

                for _ in range(pages_per_context):
                    page = await pool.acquire()
                    await pool.release(page)

        logger.info("GlobalBrowserPool warmup completed")

    @property
    def config(self) -> BrowserPoolConfig:
        """Get browser pool configuration."""
        return self._config

    @property
    def throttle_strategy(self) -> ThrottleStrategy:
        """Get rate-limiting strategy (used by Navigator)."""
        return self._throttle_strategy

    @property
    def circuit_breaker(self) -> CircuitBreaker | None:
        """Get circuit breaker (used by Navigator)."""
        return self._circuit_breaker
