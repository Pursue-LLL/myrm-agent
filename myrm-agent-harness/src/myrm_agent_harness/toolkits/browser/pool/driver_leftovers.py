"""Browsers a Playwright driver left running when it died.

A driver that is stopped closes the browsers it launched. One that is killed or crashes cannot: its browsers lose
their connection, and a headed Chromium can keep running as an orphan that no process is left to close. Every
Chromium the launcher starts carries, in its environment, the token of the driver that started it. The token names
exactly the browsers of one driver without a pid (the toolkit holds none), so the browsers of a driver known to be
dead can be ended and no other process is touched.

[INPUT]
- psutil (optional): process table scan, command line and environment reads, signalling

[OUTPUT]
- DRIVER_ENV_VAR: name of the environment variable that carries the token
- new_driver_token: a token no other driver shares
- terminate_driver_browsers: ends the browser main processes started under a token

[POS]
Used by the launcher (one token per driver, handed to every Chromium it launches; the browsers of a driver it drops
because the driver is gone are ended) and by the pool's close path (a browser whose close fails because its driver
exited). Only the token of a driver whose exit is established is ever passed in. A process is ended only when its
environment carries that token and it is a browser main process: its command line has ``--remote-debugging-pipe``,
the flag Playwright gives the browsers it launches, and no ``--type=``, which marks a helper. The helpers exit with
their main process, and an application the browser handed a link or a file to inherits the environment but is not a
browser the driver started.
"""

from __future__ import annotations

import asyncio
import logging
import secrets

logger = logging.getLogger(__name__)

DRIVER_ENV_VAR = "MYRM_BROWSER_DRIVER"

_PIPE_FLAG = "--remote-debugging-pipe"
_HELPER_FLAG_PREFIX = "--type="


def new_driver_token() -> str:
    """A token no other driver shares."""
    return secrets.token_hex(16)


def _is_browser_main_process(argv: list[str]) -> bool:
    """Whether a command line is that of a browser Playwright started, not of a helper that browser started."""
    return _PIPE_FLAG in argv and not any(arg.startswith(_HELPER_FLAG_PREFIX) for arg in argv)


def _kill_main_processes(token: str) -> int:
    """SIGKILL the browser main processes carrying ``token``; returns how many were killed."""
    try:
        import psutil
    except ImportError:
        return 0

    killed = 0
    for proc in psutil.process_iter():
        try:
            # The command line is the cheap filter; the environment is read only for a browser main process.
            if not _is_browser_main_process(proc.cmdline()) or proc.environ().get(DRIVER_ENV_VAR) != token:
                continue
            proc.kill()
            killed += 1
        except (psutil.Error, OSError, SystemError):  # SystemError: psutil on macOS (giampaolo/psutil#3024)
            continue
    return killed


async def terminate_driver_browsers(token: str) -> int:
    """End the browsers a dead driver left behind; returns how many browsers were killed.

    SIGKILL: the driver that would have closed the browser is gone, so there is nothing left to shut down in order,
    and a kill can be neither ignored nor delayed. The scan runs in a worker thread. It never raises, because it runs
    inside the recovery from a driver exit and a failed cleanup must not fail that recovery.
    """
    try:
        killed = await asyncio.to_thread(_kill_main_processes, token)
    except Exception:
        logger.warning("Could not look for browsers left behind by an exited Playwright driver", exc_info=True)
        return 0
    if killed:
        logger.warning(f"Killed {killed} browser(s) left running by an exited Playwright driver")
    return killed
