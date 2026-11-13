"""A killed Playwright driver does not strand the extension bridge: the next connect gets a new one.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser::new_agent_page (POS: a context and page the way the Agent's browser pool opens them)

[OUTPUT]
- what the Agent gets after the bridge's own Playwright driver (a Node process) is killed: one connect fails with the
  driver's error, the next one runs on a new driver and reads the user's signed-in page again, with no restart

[POS]
The end-to-end proof for the bridge's driver cache. The unit tests fake the driver, so only this test notices when
patchright stops reporting a dead driver the way `is_driver_closed_error` recognises it.
"""

from __future__ import annotations

import contextlib

import psutil
import pytest

from tests.support.extension_real_browser import INTRANET_HOST, RealExtensionStack, new_agent_page

pytestmark = pytest.mark.e2e


def _driver_processes() -> dict[int, psutil.Process]:
    """The Playwright drivers (the bundled `driver/node` executable) this test process started."""
    drivers: dict[int, psutil.Process] = {}
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):  # a Chromium helper may exit while the list is walked
            argv = child.cmdline()
            if argv and "/driver/" in argv[0].replace("\\", "/"):
                drivers[child.pid] = child
    return drivers


async def _read_the_signed_in_page(stack: RealExtensionStack) -> str:
    """What the Agent reads on the user's intranet page, through a fresh connect of the bridge."""
    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))
        return await page.inner_text("#data")


async def test_a_connect_after_the_bridge_driver_was_killed_runs_on_a_new_driver(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    before = set(_driver_processes())
    assert await _read_the_signed_in_page(stack) == "private-data-42"
    started = {pid: proc for pid, proc in _driver_processes().items() if pid not in before}
    assert len(started) == 1, f"expected the bridge to have started one driver, found {sorted(started)}"
    for driver in started.values():
        driver.kill()

    with pytest.raises(Exception, match="Connection closed while reading from the driver"):
        await _read_the_signed_in_page(stack)

    assert await _read_the_signed_in_page(stack) == "private-data-42"
    replacements = set(_driver_processes()) - before - set(started)  # the killed driver may linger as a zombie
    assert len(replacements) == 1, f"expected one replacement driver, found {sorted(replacements)}"
