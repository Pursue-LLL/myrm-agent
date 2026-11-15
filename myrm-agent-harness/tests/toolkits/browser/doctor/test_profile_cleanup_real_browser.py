"""Real-Chromium proof that a killed Playwright driver leaves its profile behind and the Doctor removes it.

Playwright deletes the throw-away profile of a browser only when that browser is closed through its driver, so a
browser that goes down with the driver leaves the directory in the temp directory. The prune must keep the
directory while a browser runs on it and remove it once no process uses it.
Run with: `pytest -m integration tests/toolkits/browser/doctor/test_profile_cleanup_real_browser.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from collections.abc import Collection
from pathlib import Path

import psutil
import pytest

from myrm_agent_harness.toolkits.browser.doctor import cleanup_stale_browser_profiles
from myrm_agent_harness.toolkits.browser.doctor.orphans import extract_user_data_dir
from tests.toolkits.browser._browser_available import chromium_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_STEP_TIMEOUT_S = 15.0


def _processes_using(profile: Path) -> list[psutil.Process]:
    """Processes that run with ``profile`` as their ``--user-data-dir``."""
    users: list[psutil.Process] = []
    for proc in psutil.process_iter():
        with contextlib.suppress(psutil.Error, OSError, SystemError):  # another user's or just exited
            if extract_user_data_dir(proc.cmdline()) == str(profile):
                users.append(proc)
    return users


def _drivers(ignoring: Collection[int] = ()) -> list[psutil.Process]:
    """The Playwright drivers (the bundled ``driver/node`` executable) running below this process.

    The pids in *ignoring* are left out.
    """
    drivers: list[psutil.Process] = []
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):
            argv = child.cmdline()
            if child.pid not in ignoring and argv and "/driver/" in argv[0].replace("\\", "/"):
                drivers.append(child)
    return drivers


def _browser_family(profile: Path) -> list[psutil.Process]:
    """The browser running on ``profile`` and every process below it.

    Its GPU and network service processes carry no ``--user-data-dir`` yet keep writing into the profile until they exit.
    """
    family: dict[int, psutil.Process] = {}
    for browser in _processes_using(profile):
        family[browser.pid] = browser
        with contextlib.suppress(psutil.NoSuchProcess):
            family.update((child.pid, child) for child in browser.children(recursive=True))
    return list(family.values())


def _kill(proc: psutil.Process) -> None:
    """SIGKILL ``proc``; one that exited by itself since it was listed is as gone as one that was killed."""
    with contextlib.suppress(psutil.NoSuchProcess):
        proc.kill()


def _is_alive(proc: psutil.Process) -> bool:
    """Whether ``proc`` still runs; a zombie has exited and only waits for its parent to collect it."""
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


async def test_a_profile_a_killed_driver_leaves_behind_is_removed_once_no_browser_uses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from patchright.async_api import async_playwright

    # The driver reads TMPDIR when it starts, so the browser's profile lands in the test's directory, not the real one.
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    # The tests of a run share this process, so a driver an earlier test left running is neither this test's driver nor
    # one to kill with it.
    left_running = {driver.pid for driver in _drivers()}
    playwright = await async_playwright().start()
    try:
        await playwright.chromium.launch(headless=True)
        (profile,) = tmp_path.glob("playwright_chromiumdev_profile-*")
        assert _processes_using(profile), "the browser must run on the profile for this test to mean anything"

        assert cleanup_stale_browser_profiles(max_age_hours=0.0)["pruned"] == 0, "a running browser keeps its profile"

        (driver,) = _drivers(ignoring=left_running)
        # Listed while the browser runs: once its main process is gone, nothing ties its children to the profile.
        browser = _browser_family(profile)
        _kill(driver)
        # A headless Chromium ends by itself, a headed one can outlive the driver; either way it is gone.
        for proc in browser:
            _kill(proc)
        async with asyncio.timeout(_STEP_TIMEOUT_S):
            while any(_is_alive(proc) for proc in browser) or _processes_using(profile):
                await asyncio.sleep(0.1)

        assert profile.exists(), "nothing but a graceful close through the driver deletes the profile"
        preview = cleanup_stale_browser_profiles(max_age_hours=0.0)
        assert preview["pruned"] == 1
        assert profile.exists()

        result = cleanup_stale_browser_profiles(max_age_hours=0.0, dry_run=False)

        assert result["pruned"] == 1
        assert result["reclaimed_bytes"] == preview["reclaimed_bytes"] > 0
        assert result["failed"] == []
        assert not profile.exists()
    finally:
        for driver in _drivers(ignoring=left_running):
            _kill(driver)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(playwright.stop(), timeout=_STEP_TIMEOUT_S)
