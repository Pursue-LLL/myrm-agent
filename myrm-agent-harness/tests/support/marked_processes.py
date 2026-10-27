"""Find, wait for and remove external processes by a marker in their command line.

[INPUT]
- psutil (POS: process listing that needs no pgrep/pkill binaries)

[OUTPUT]
- process_alive: whether a worker process whose command line contains the marker is running (a shell that only carries
  the marker as script text does not count)
- kill_marked: remove every such worker process (test teardown)
- wait_until: poll a condition until it holds or a deadline passes

[POS]
Harness pytest-only helper for stop/cancel tests that must prove a sleeper they started is running before the stop and
gone after it, on any platform and without relying on external process utilities.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable

import psutil

_POLL_S = 0.05
# A shell started with `-c <script>` carries the script text, marker included, before the worker it will spawn exists.
_SHELLS = frozenset({"sh", "bash", "dash", "zsh"})


def _marked(marker: str) -> list[psutil.Process]:
    own_pid = os.getpid()
    found: list[psutil.Process] = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        cmdline = process.info["cmdline"] or []
        if process.info["pid"] == own_pid or process.info["name"] in _SHELLS:
            continue
        if marker in " ".join(cmdline):
            found.append(process)
    return found


def process_alive(marker: str) -> bool:
    return bool(_marked(marker))


def kill_marked(marker: str) -> None:
    for process in _marked(marker):
        with contextlib.suppress(psutil.Error):
            process.kill()


async def wait_until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(_POLL_S)
