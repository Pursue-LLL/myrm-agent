"""Chromium launched by the pool launcher is stamped and recognised as Chromium; the driver and this process are not."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time

import psutil
import pytest

from myrm_agent_harness.toolkits.browser.doctor.orphans import _is_chromium_process
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserLauncher
from myrm_agent_harness.toolkits.browser.process_owner import OWNER_ENV_VAR, OwnerState, read_owner_state
from tests.toolkits.browser._browser_available import chromium_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium/Patchright not installed in this environment"),
]

_HELPER_STARTUP_TIMEOUT_S = 10.0


def _driver_of(parent: psutil.Process) -> psutil.Process:
    """The patchright driver child; reading a reaped child's cmdline raises instead of answering."""
    for proc in parent.children(recursive=True):
        try:
            if "run-driver" in " ".join(proc.cmdline()):
                return proc
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            continue
    msg = "patchright driver process not found"
    raise LookupError(msg)


def _browser_processes(driver: psutil.Process) -> list[psutil.Process]:
    """Live Chromium processes under the driver, or under this process when the driver spawns none.

    On macOS the driver forks the browser, so the driver's children are the browser tree. A Linux
    container may instead launch the browser beside the driver, where the driver has no children at
    all; looking only below it would then sample an empty set.
    """
    found = [proc for proc in driver.children(recursive=True) if _is_alive(proc)]
    if found:
        return found
    return [
        proc
        for proc in psutil.Process().children(recursive=True)
        if _is_alive(proc) and _is_chromium_process(proc)
    ]


async def _wait_for_browser_processes(driver: psutil.Process) -> list[psutil.Process]:
    """The browser main process and at least one helper; Chromium starts its helpers right after the main process."""
    deadline = time.monotonic() + _HELPER_STARTUP_TIMEOUT_S
    while True:
        processes = _browser_processes(driver)
        if len(processes) >= 2 or time.monotonic() >= deadline:
            return processes
        await asyncio.sleep(0.1)


def _is_alive(proc: psutil.Process) -> bool:
    """A listed child may be reaped or turn into a zombie between listing and use."""
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        return False


def _owner_states(processes: list[psutil.Process]) -> dict[int, OwnerState]:
    states: dict[int, OwnerState] = {}
    for proc in processes:
        # Only a process that vanished between listing and reading is skipped; an unreadable
        # environment is a state (UNKNOWN) that read_owner_state already reports.
        with contextlib.suppress(psutil.NoSuchProcess, psutil.ZombieProcess):
            states[proc.pid] = read_owner_state(proc)
    return states


def _not_recognised_as_chromium(processes: list[psutil.Process]) -> list[str]:
    """Names of the running processes the orphan check would take for something other than Chromium."""
    names: list[str] = []
    for proc in processes:
        # Reading a reaped or zombie child raises instead of answering; it is not a Chromium miss.
        with contextlib.suppress(psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            if proc.is_running() and not _is_chromium_process(proc):
                names.append(proc.name())
    return names


async def test_launched_chromium_is_stamped_and_nothing_else_is() -> None:
    launcher = BrowserLauncher(launch_options={"headless": True})
    instance = await launcher.create_browser()
    try:
        driver = _driver_of(psutil.Process())
        browser_processes = await _wait_for_browser_processes(driver)
        states = _owner_states(browser_processes)

        assert len(states) >= 2
        # Chromium's helper processes do not all inherit the launch environment — Linux starts zygote and
        # crashpad children that rewrite it — so the ownership proof is the browser main process carrying the
        # stamp, not every descendant carrying it. A stamped process must never look like a leftover, and at
        # least one browser process must be stamped for the orphan check to have something to judge.
        stamped = [pid for pid, state in states.items() if state is OwnerState.OWNER_ALIVE]
        assert stamped, f"no browser process carried the ownership stamp: {states}"
        assert OwnerState.OWNER_GONE not in set(states.values())
        assert set(states.values()) <= {OwnerState.OWNER_ALIVE, OwnerState.UNSTAMPED}
        assert _not_recognised_as_chromium(browser_processes) == []
        assert read_owner_state(driver) is OwnerState.UNSTAMPED
        assert OWNER_ENV_VAR not in os.environ
    finally:
        with contextlib.suppress(Exception):
            await instance.browser.close()
        await launcher.shutdown()
