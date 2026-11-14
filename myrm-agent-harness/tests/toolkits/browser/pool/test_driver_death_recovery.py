"""Real-Chromium proof that everything above a killed Playwright driver serves again without waiting for anything.

The driver is the Node process every launched browser hangs off. Killing it leaves the browser unreachable (a headless
one exits, a headed one can keep running), yet the browser object still reports itself connected and fires no
'disconnected' event. The call that hits the dead driver is the first to know, so it evicts the dead browser, ends
whatever of it is still running and goes on to a new one itself: the pool, a tool call on a session and a pool
attached to a remote browser all recover without a periodic tick or a second request.
Run with: `pytest -m integration tests/toolkits/browser/pool/test_driver_death_recovery.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path

import psutil
import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.pool.config import BrowserPoolConfig, LaunchMode
from myrm_agent_harness.toolkits.browser.process_owner import OWNER_ENV_VAR, owner_stamp_env
from myrm_agent_harness.toolkits.browser.tools import create_browser_tools
from myrm_agent_harness.toolkits.browser.utils.page_health import is_driver_closed_error
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._stall_servers import StallServers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_CONTEXT_KEY = "driver-death"
_RECOVERY_TIMEOUT_S = 60.0
_TEARDOWN_TIMEOUT_S = 20.0
_REMOTE_START_TIMEOUT_S = 30.0
_ENDED_TIMEOUT_S = 10.0
_BROWSER_MAIN_PROCESS_FLAG = "--remote-debugging-pipe"


async def _shutdown(pool: GlobalBrowserPool) -> None:
    with contextlib.suppress(Exception):
        await asyncio.wait_for(pool.shutdown(), timeout=_TEARDOWN_TIMEOUT_S)


@pytest.fixture
async def pool() -> AsyncIterator[GlobalBrowserPool]:
    browser_pool = GlobalBrowserPool(max_browsers=1)
    yield browser_pool
    await _shutdown(browser_pool)


@pytest.fixture
async def remote_chromium(tmp_path: Path) -> AsyncIterator[str]:
    """A Chromium started outside any Playwright driver, reachable over its CDP websocket (what REMOTE mode attaches to)."""
    from patchright.async_api import async_playwright

    async with async_playwright() as playwright:
        executable = playwright.chromium.executable_path
    profile = tmp_path / "profile"
    process = subprocess.Popen(
        [executable, "--headless=new", "--remote-debugging-port=0", "--no-sandbox", f"--user-data-dir={profile}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        port_file = profile / "DevToolsActivePort"  # Chromium writes the port it picked and the websocket path
        async with asyncio.timeout(_REMOTE_START_TIMEOUT_S):
            while not (port_file.exists() and len(port_file.read_text().split()) >= 2):
                await asyncio.sleep(0.2)
        port, path = port_file.read_text().split()[:2]
        yield f"ws://127.0.0.1:{port}{path}"
    finally:
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, _TEARDOWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()


def _driver_processes() -> dict[int, psutil.Process]:
    """The Playwright drivers this process started (the bundled `driver/node` executable)."""
    drivers: dict[int, psutil.Process] = {}
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):  # a Chromium helper may exit while the list is walked
            argv = child.cmdline()
            if argv and "/driver/" in argv[0].replace("\\", "/"):
                drivers[child.pid] = child
    return drivers


def _kill_the_driver_started_since(before: set[int]) -> set[int]:
    """SIGKILL the one driver that appeared after `before`. Returns its pid."""
    started = {pid: proc for pid, proc in _driver_processes().items() if pid not in before}
    assert len(started) == 1, f"expected exactly one new driver process, found {sorted(started)}"
    for driver in started.values():
        driver.kill()
    return set(started)


def _assert_one_replacement_driver(before: set[int], killed: set[int]) -> None:
    replacements = set(_driver_processes()) - before - killed  # the killed driver may linger as a zombie
    assert len(replacements) == 1, f"expected exactly one new driver process, found {sorted(replacements)}"


def _browser_main_processes() -> dict[int, psutil.Process]:
    """The browser main processes this process launched: Playwright gives them the pipe flag, the launcher the stamp.

    A helper (`--type=...`) carries the flag too and is not a browser. Found through the stamp, not through the
    driver: a Linux container may start the browser beside the driver.
    """
    stamp = owner_stamp_env()[OWNER_ENV_VAR]
    browsers: dict[int, psutil.Process] = {}
    for proc in psutil.process_iter():
        # A process of another user, or one that just exited, cannot be read and is none of ours.
        with contextlib.suppress(psutil.Error, OSError, SystemError):
            argv = proc.cmdline()
            is_main = _BROWSER_MAIN_PROCESS_FLAG in argv and not any(arg.startswith("--type=") for arg in argv)
            if is_main and proc.environ().get(OWNER_ENV_VAR) == stamp:
                browsers[proc.pid] = proc
    return browsers


async def _ends_within(process: psutil.Process, timeout_s: float) -> bool:
    """Whether `process` is gone, or only a zombie waiting to be reaped, within `timeout_s`."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if process.status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(0.1)


async def _page_answers(pool: GlobalBrowserPool) -> bool:
    page, key = await pool.acquire_page(ContextType.AGENT, context_key=_CONTEXT_KEY)
    try:
        return bool(await page.evaluate("1 + 1") == 2)
    finally:
        await pool.release_page(page, key)


async def _warm_up_and_kill_the_driver(pool: GlobalBrowserPool) -> tuple[set[int], set[int]]:
    """Serve one page, then SIGKILL the driver the pool started. Returns (drivers before the pool, drivers killed)."""
    before = set(_driver_processes())
    assert await _page_answers(pool)
    return before, _kill_the_driver_started_since(before)


async def test_the_first_acquisition_after_the_driver_is_killed_is_served(pool: GlobalBrowserPool) -> None:
    before, killed = await _warm_up_and_kill_the_driver(pool)

    async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
        assert await _page_answers(pool)
        assert await _page_answers(pool)

    _assert_one_replacement_driver(before, killed)
    assert pool._global_semaphore._value == pool._config.max_concurrent_pages, "a permit leaked in the recovery"


async def test_callers_arriving_together_after_the_driver_died_are_all_served(pool: GlobalBrowserPool) -> None:
    before, killed = await _warm_up_and_kill_the_driver(pool)

    async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
        answers = await asyncio.gather(*[_page_answers(pool) for _ in range(3)])

    assert answers == [True, True, True]
    _assert_one_replacement_driver(before, killed)


async def test_the_lifecycle_tick_alone_evicts_the_browser_a_killed_driver_left_behind(
    pool: GlobalBrowserPool,
) -> None:
    """With no acquisition to notice it, the periodic tick is still what clears the dead browser out."""
    await _warm_up_and_kill_the_driver(pool)

    await pool._lifecycle_tick()

    assert pool._browsers == []
    assert pool._global_semaphore._value == pool._config.max_concurrent_pages
    async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
        assert await _page_answers(pool)


async def test_a_browser_that_outlives_its_killed_driver_is_ended(pool: GlobalBrowserPool) -> None:
    """A headed Chromium can keep running after its driver is killed, and no process is left to close it.

    Suspending the browser first makes any browser behave like that on every platform: it cannot notice that its
    driver is gone, so only the pool can end it.
    """
    browsers_before = set(_browser_main_processes())
    before = set(_driver_processes())
    assert await _page_answers(pool)
    launched = [proc for pid, proc in _browser_main_processes().items() if pid not in browsers_before]
    assert len(launched) == 1, f"expected exactly one new browser main process, found {launched}"
    (orphan,) = launched
    try:
        orphan.suspend()
        killed = _kill_the_driver_started_since(before)

        async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
            assert await _page_answers(pool)

        assert await _ends_within(orphan, _ENDED_TIMEOUT_S), "the browser the dead driver left behind still runs"
        _assert_one_replacement_driver(before, killed)
    finally:
        with contextlib.suppress(psutil.Error):
            orphan.kill()


async def test_a_tool_call_on_a_killed_driver_fails_once_and_the_session_is_healed(pool: GlobalBrowserPool) -> None:
    """The failed call is the model's signal; the tab it died on is already replaced when the next call comes."""
    session = BrowserSession(pool, ContextType.AGENT, allow_private_networks=True)
    async with StallServers(slow_delay_s=0.5) as servers:
        try:
            before = set(_driver_processes())
            await session.new_tab()
            tools = {tool.name: tool for tool in create_browser_tools(session)}
            assert "title=Good" in str(await tools["browser_navigate_tool"].ainvoke({"url": servers.ok}))
            killed = _kill_the_driver_started_since(before)

            async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
                with pytest.raises(Exception, match=r".+") as failure:
                    await tools["browser_navigate_tool"].ainvoke({"url": servers.ok})
                assert is_driver_closed_error(failure.value)
                announced = str(await tools["browser_snapshot_tool"].ainvoke({}))
                served = str(await tools["browser_navigate_tool"].ainvoke({"url": servers.ok}))

            assert "reset to a blank page" in announced, "the model must be told its tab was replaced"
            assert "title=Good" in served
            assert len(session.list_tabs()) == 1
            _assert_one_replacement_driver(before, killed)
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(session.close(), timeout=_TEARDOWN_TIMEOUT_S)


async def test_a_pool_attached_to_a_remote_browser_serves_again_after_its_driver_is_killed(
    remote_chromium: str,
) -> None:
    """Remote and CDP-connected pools reach the browser through the driver too, and the browser outlives it."""
    config = dataclasses.replace(
        BrowserPoolConfig.minimal(), launch_mode=LaunchMode.REMOTE, remote_ws_endpoint=remote_chromium
    )
    pool = GlobalBrowserPool(max_browsers=1, config=config)
    try:
        before, killed = await _warm_up_and_kill_the_driver(pool)

        async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
            assert await _page_answers(pool)

        _assert_one_replacement_driver(before, killed)
    finally:
        await _shutdown(pool)
