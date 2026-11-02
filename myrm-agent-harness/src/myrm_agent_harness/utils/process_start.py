"""A process's start time, stable across system clock adjustments.

On Linux psutil reports a start time as the boot time plus the ticks since boot, and the boot time follows the wall
clock (NTP steps, a VM resumed with a corrected clock), so one process reports a different start time after a clock
step. ``start_stamp`` removes the boot time there. On macOS psutil corrects for clock steps itself and on Windows the
start time is the instant the OS recorded, so both are returned as they are; no other platform is assessed.
Two stamps of one process agree within the rounding of the platform's clock ticks, so compare them with a tolerance
rather than for equality; a different process that took over the pid starts at another time and differs by more.

Build the ``psutil.Process`` for every read. A process object keeps the start time it first reported, so one that
reported before a clock step yields a stamp the step has moved; the objects ``psutil.process_iter`` hands out are
cached between calls and are such objects.

[INPUT]
- psutil (POS: process table access: a process's start time and the boot time; imported when a stamp is read, so this
  module imports without it)

[OUTPUT]
- start_stamp: the start time of a process in seconds, comparable across system clock adjustments

[POS]
Shared by the browser ownership stamp and the background job termination, which both decide from a recorded start time
whether a pid still names the process they recorded.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psutil

_START_TIMES_FOLLOW_WALL_CLOCK = sys.platform.startswith("linux")


def start_stamp(proc: psutil.Process) -> float:
    """The start time of ``proc`` in seconds, comparable across system clock adjustments.

    ``proc`` must be a ``psutil.Process`` built for this read.
    """
    import psutil

    started = proc.create_time()
    if _START_TIMES_FOLLOW_WALL_CLOCK:
        started -= psutil.boot_time()
    return started


__all__ = ["start_stamp"]
