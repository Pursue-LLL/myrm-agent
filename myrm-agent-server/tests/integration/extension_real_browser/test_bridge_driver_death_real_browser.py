"""A killed Playwright driver does not strand the extension bridge: the next connect gets a new one.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser::new_agent_page (POS: a context and page the way the Agent's browser pool opens them)
- myrm_agent_harness.api::is_driver_closed_error (POS: tells the failure the dead driver causes from any other)

[OUTPUT]
- what the Agent gets after the bridge's own Playwright driver (a Node process) is killed: a connect is served by a new
  driver in the same call and reads the user's signed-in page, and a browsing session fails once on the call that finds
  the driver dead, has its tab replaced and announced, then works, all with no restart

[POS]
The end-to-end proof for the bridge's driver cache. The unit tests fake the driver, so only these tests notice when
patchright stops reporting a dead driver the way `is_driver_closed_error` recognises it.
"""

from __future__ import annotations

import asyncio
import contextlib

import psutil
import pytest
from myrm_agent_harness.api import is_driver_closed_error
from myrm_agent_harness.toolkits.browser.tools import create_browser_tools

from tests.support.extension_real_browser import INTRANET_HOST, RealExtensionStack, new_agent_page

pytestmark = pytest.mark.e2e

_RECOVERY_TIMEOUT_S = 60.0


def _driver_processes() -> dict[int, psutil.Process]:
    """The Playwright drivers (the bundled `driver/node` executable) this test process started."""
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
    assert len(started) == 1, f"expected the bridge to have started one driver, found {sorted(started)}"
    for driver in started.values():
        driver.kill()
    return set(started)


def _assert_one_replacement_driver(before: set[int], killed: set[int]) -> None:
    replacements = set(_driver_processes()) - before - killed  # the killed driver may linger as a zombie
    assert len(replacements) == 1, f"expected one replacement driver, found {sorted(replacements)}"


async def _read_the_signed_in_page(stack: RealExtensionStack) -> str:
    """What the Agent reads on the user's intranet page, through a fresh connect of the bridge."""
    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))
        return await page.inner_text("#data")


async def test_a_connect_after_the_bridge_driver_was_killed_is_served_by_a_new_driver(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    before = set(_driver_processes())
    assert await _read_the_signed_in_page(stack) == "private-data-42"
    killed = _kill_the_driver_started_since(before)

    async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
        assert await _read_the_signed_in_page(stack) == "private-data-42"

    _assert_one_replacement_driver(before, killed)


async def test_a_session_fails_once_on_the_call_that_finds_the_driver_dead_then_works(stack: RealExtensionStack) -> None:
    """The failed call is the model's signal; the tab it died on is already replaced when the next call comes."""
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    secret = stack.site.url(INTRANET_HOST, "/secret")
    before = set(_driver_processes())

    async with stack.agent_session() as session:
        await session.new_tab()
        tools = {tool.name: tool for tool in create_browser_tools(session)}
        assert "title=Secret" in str(await tools["browser_navigate_tool"].ainvoke({"url": secret}))
        killed = _kill_the_driver_started_since(before)

        async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
            with pytest.raises(Exception, match=r".+") as failure:
                await tools["browser_navigate_tool"].ainvoke({"url": secret})
            assert is_driver_closed_error(failure.value)
            announced = str(await tools["browser_snapshot_tool"].ainvoke({}))
            served = str(await tools["browser_navigate_tool"].ainvoke({"url": secret}))

    assert "reset to a blank page" in announced, "the model must be told its tab was replaced"
    assert "title=Secret" in served
    _assert_one_replacement_driver(before, killed)
