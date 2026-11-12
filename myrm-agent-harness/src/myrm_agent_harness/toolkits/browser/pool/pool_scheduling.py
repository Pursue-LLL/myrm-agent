"""Browser scheduling for the global pool: one launcher per engine and launch mode, and the least-loaded browser.

[INPUT]
- .browser_launcher::BrowserLauncher, BrowserInstance (POS: browser launcher and instance metadata)
- .config::BrowserEngine, BrowserPoolConfig, LaunchMode, MAX_CONTEXTS_PER_BROWSER, SCALE_OUT_LOAD_THRESHOLD (POS: pool configuration and scheduling limits)
- .extension_bridge::ExtensionBridge (POS: bridge the EXTENSION launcher connects through)

[OUTPUT]
- PoolSchedulingMixin: `_get_launcher` and `_get_least_loaded_browser` for GlobalBrowserPool

[POS]
Decides which browser serves a request. A request for an external launch mode (connect, extension) is served only by a
browser the pool did not launch, and any other mode only by one it launched. Among those the least-loaded browser that
has contexts to spare wins; when it is busy and `max_browsers` allows, another browser is created, and when every
browser is full the least-loaded one takes the context anyway.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .browser_launcher import BrowserInstance, BrowserLauncher
from .config import (
    MAX_CONTEXTS_PER_BROWSER,
    SCALE_OUT_LOAD_THRESHOLD,
    BrowserEngine,
    BrowserPoolConfig,
    LaunchMode,
)

if TYPE_CHECKING:
    from .extension_bridge import ExtensionBridge

logger = logging.getLogger(__name__)


class PoolSchedulingMixin:
    """Launcher cache and load-aware browser selection for GlobalBrowserPool.

    Requires host class to have:
    - _browsers: list[BrowserInstance]
    - _max_browsers: int
    - _config: BrowserPoolConfig
    - _launchers: dict[tuple[BrowserEngine, LaunchMode], BrowserLauncher]
    - _launch_options: dict[str, object]
    - _extension_bridge: ExtensionBridge | None
    """

    _browsers: list[BrowserInstance]
    _max_browsers: int
    _config: BrowserPoolConfig
    _launchers: dict[tuple[BrowserEngine, LaunchMode], BrowserLauncher]
    _launch_options: dict[str, object]
    _extension_bridge: ExtensionBridge | None

    if TYPE_CHECKING:

        def _register_disconnect_handler(self, inst: BrowserInstance) -> None: ...

    def _get_launcher(self, engine: BrowserEngine, launch_mode: LaunchMode | None = None) -> BrowserLauncher:
        """Get or create a BrowserLauncher for the specified engine and launch mode."""
        effective_mode = launch_mode or self._config.launch_mode
        key = (engine, effective_mode)
        if key not in self._launchers:
            fp_dir = self._resolve_fingerprint_dir() if engine == BrowserEngine.FIREFOX_CAMOUFOX else None
            self._launchers[key] = BrowserLauncher(
                launch_options=self._launch_options,
                launch_mode=effective_mode,
                engine=engine,
                cdp_endpoint=self._config.cdp_endpoint,
                remote_ws_endpoint=self._config.remote_ws_endpoint,
                remote_ws_headers=self._config.remote_ws_headers,
                extension_bridge=self._extension_bridge,
                fingerprint_dir=fp_dir,
            )
        return self._launchers[key]

    @staticmethod
    def _resolve_fingerprint_dir() -> Path:
        """Resolve the directory for persisting Camoufox fingerprints.

        Uses ``$MYRM_DATA_DIR/browser_fingerprints`` when the env var is set,
        otherwise falls back to ``$CWD/.myrm/browser_fingerprints``.
        """
        base = os.environ.get("MYRM_DATA_DIR") or os.path.join(os.getcwd(), ".myrm")
        return Path(base) / "browser_fingerprints"

    async def _get_least_loaded_browser(
        self, engine: BrowserEngine, launch_mode: LaunchMode | None = None
    ) -> BrowserInstance:
        """Load-aware scheduling — select the least-loaded Browser for the given engine.

        Prefers Browsers that have not reached max_contexts_per_browser.
        When all Browsers are heavily loaded, auto-scales by creating new Browsers (up to max_browsers).
        When max_browsers is reached, logs a warning and force-assigns to the least-loaded Browser.
        """
        launcher = self._get_launcher(engine, launch_mode)
        effective_mode = launch_mode or self._config.launch_mode
        prefer_external_browser = effective_mode in (LaunchMode.EXTENSION, LaunchMode.CONNECT)

        if not self._browsers:
            inst = await launcher.create_browser()
            self._register_disconnect_handler(inst)
            self._browsers.append(inst)
            return inst

        engine_browsers = [
            b for b in self._browsers if b.engine == engine.value and b.is_managed != prefer_external_browser
        ]

        if not engine_browsers:
            inst = await launcher.create_browser()
            self._register_disconnect_handler(inst)
            self._browsers.append(inst)
            return inst

        # Prefer Browsers that have not reached contexts limit
        available_browsers = [b for b in engine_browsers if len(b.contexts) < MAX_CONTEXTS_PER_BROWSER]

        if available_browsers:
            least = min(available_browsers, key=lambda b: b.load)

            # If least-loaded Browser is still busy and max_browsers not reached, create new one
            if least.load > SCALE_OUT_LOAD_THRESHOLD and len(self._browsers) < self._max_browsers:
                inst = await launcher.create_browser()
                self._register_disconnect_handler(inst)
                self._browsers.append(inst)
                return inst

            return least

        # All Browsers reached contexts limit
        if len(self._browsers) < self._max_browsers:
            inst = await launcher.create_browser()
            self._register_disconnect_handler(inst)
            self._browsers.append(inst)
            return inst

        # max_browsers reached, log warning and force-assign
        logger.warning(
            f"All browsers at max_contexts_per_browser limit ({MAX_CONTEXTS_PER_BROWSER}), "
            f"forcing context creation on least loaded browser",
        )
        return min(engine_browsers, key=lambda b: b.load)
