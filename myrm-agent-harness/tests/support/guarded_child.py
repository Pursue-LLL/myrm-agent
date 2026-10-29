"""Run a Python snippet in a child process that is killed when it outgrows a memory or time budget.

[INPUT]
- psutil (POS: resident-memory sampling of the child without platform-specific resource calls)
- myrm_agent_harness (POS: the package under test, put on the child's import path explicitly)

[OUTPUT]
- run_guarded: run a snippet and report how it ended (finished, over the memory budget, or past the deadline)
- GuardedRun: the outcome, with the child's stdout/stderr, return code and peak resident memory

[POS]
Shared by the tests that feed the harness a hostile file (an endless device, a FIFO, a sparse multi-gigabyte file): an
unbounded read or a blocking open would otherwise exhaust memory or hang the test run, so a regression has to fail as an
ordinary assertion instead. The child is a fresh interpreter, so the snippet sees the package exactly as a user process
would.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

import myrm_agent_harness

_POLL_S = 0.02
_MB = 1024 * 1024
_PACKAGE_PARENT = str(Path(myrm_agent_harness.__file__).resolve().parent.parent)


@dataclass(frozen=True, slots=True)
class GuardedRun:
    """How a guarded child ended."""

    returncode: int | None
    stdout: str
    stderr: str
    peak_rss_mb: float
    over_memory: bool
    timed_out: bool

    @property
    def finished(self) -> bool:
        """True when the child ended by itself, within both budgets."""
        return not (self.over_memory or self.timed_out)


def run_guarded(code: str, *, max_rss_mb: int = 256, timeout_s: float = 30.0) -> GuardedRun:
    """Run *code* with ``python -c`` and kill it once it holds more than *max_rss_mb* or runs past *timeout_s*."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [_PACKAGE_PARENT, os.environ.get("PYTHONPATH")]))}
    with subprocess.Popen(
        [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env
    ) as child:
        watched = psutil.Process(child.pid)
        deadline = time.monotonic() + timeout_s
        peak = 0
        over_memory = timed_out = False
        while child.poll() is None:
            try:
                peak = max(peak, watched.memory_info().rss)
            except psutil.NoSuchProcess:
                break
            if peak > max_rss_mb * _MB:
                over_memory = True
                child.kill()
                break
            if time.monotonic() > deadline:
                timed_out = True
                child.kill()
                break
            time.sleep(_POLL_S)
        stdout, stderr = child.communicate()
    return GuardedRun(child.returncode, stdout, stderr, peak / _MB, over_memory, timed_out)
