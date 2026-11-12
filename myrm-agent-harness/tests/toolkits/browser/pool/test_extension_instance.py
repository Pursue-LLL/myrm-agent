"""The user's own browser, reached through the extension, is told apart from a launched or CDP-attached one.

The pool decides everything that follows from the instance kind: a context in the user's browser asks it for no
override, and its pages are never kept idle, so a tab the Agent let go of closes instead of staying open in the
user's window. A CDP-attached browser keeps the pool's usual treatment.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserInstance
from myrm_agent_harness.toolkits.browser.pool.config import BrowserEngine, BrowserPoolConfig, LaunchMode
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBrowserInstance
from tests.toolkits.browser._fake_pages import FakeCdp, FakePage

_KEY = "ctx"


def _pool_serving(inst: BrowserInstance, monkeypatch: pytest.MonkeyPatch) -> tuple[GlobalBrowserPool, AsyncMock]:
    """A real pool whose only browser is `inst`; its context factory answers with a context of fake pages."""
    pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal())
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=lambda: FakePage(cdp=FakeCdp()))
    create_context = AsyncMock(return_value=context)
    monkeypatch.setattr(pool._context_factory, "create_context", create_context)
    pool._browsers.append(inst)
    monkeypatch.setattr(pool, "_get_least_loaded_browser", AsyncMock(return_value=inst))
    monkeypatch.setattr(pool, "_ensure_lifecycle_loop", MagicMock())
    monkeypatch.setattr(pool._memory_guard, "check_memory", AsyncMock())
    return pool, create_context


async def _take_and_release(pool: GlobalBrowserPool, launch_mode: LaunchMode) -> FakePage:
    """Acquire and release a page through the pool under test (its browser is a double, so no real browser starts)."""
    page, key = await pool.acquire_page(ContextType.AGENT, context_key=_KEY, launch_mode_preference=launch_mode)
    await pool.release_page(page, key)
    return page


class TestExtensionBrowserInstance:
    def test_it_is_a_browser_the_pool_did_not_launch(self) -> None:
        inst = ExtensionBrowserInstance(browser=MagicMock())

        assert inst.is_managed is False
        assert inst.engine == BrowserEngine.CHROMIUM_PATCHRIGHT.value

    async def test_every_later_request_for_the_extension_is_served_by_the_same_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pool = GlobalBrowserPool(max_browsers=3, config=BrowserPoolConfig.minimal())
        launcher = MagicMock()
        launcher.create_browser = AsyncMock(side_effect=lambda: ExtensionBrowserInstance(browser=MagicMock()))
        monkeypatch.setattr(pool, "_get_launcher", MagicMock(return_value=launcher))

        first = await pool._get_least_loaded_browser(BrowserEngine.CHROMIUM_PATCHRIGHT, LaunchMode.EXTENSION)
        again = await pool._get_least_loaded_browser(BrowserEngine.CHROMIUM_PATCHRIGHT, LaunchMode.EXTENSION)

        assert again is first
        launcher.create_browser.assert_awaited_once()


class TestPoolTreatsTheUsersBrowserDifferently:
    async def test_its_contexts_ask_for_no_override_and_its_pages_are_not_kept_idle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inst = ExtensionBrowserInstance(browser=MagicMock())
        pool, create_context = _pool_serving(inst, monkeypatch)

        page = await _take_and_release(pool, LaunchMode.EXTENSION)

        assert create_context.await_args.kwargs["extension_attached"] is True
        assert page.close_calls == 1
        assert inst.page_pools[_KEY].stats["idle"] == 0

    async def test_a_cdp_attached_browser_keeps_the_usual_context_and_idle_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inst = BrowserInstance(browser=MagicMock(), is_managed=False)
        pool, create_context = _pool_serving(inst, monkeypatch)

        page = await _take_and_release(pool, LaunchMode.CONNECT)

        assert create_context.await_args.kwargs["extension_attached"] is False
        assert page.close_calls == 0
        assert inst.page_pools[_KEY].stats["idle"] == 1
