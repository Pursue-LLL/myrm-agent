"""A process's start stamp: the same on every read, whatever the system clock does."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import psutil
import pytest

from myrm_agent_harness.utils import process_start
from myrm_agent_harness.utils.process_start import start_stamp

_BOOT_TIME = 1_700_000_000.0
_TICKS_SINCE_BOOT = 5_000.0


def _started_at(created: float) -> psutil.Process:
    """A stand-in for a psutil process whose wall-clock start time reads as ``created``."""
    return cast("psutil.Process", SimpleNamespace(create_time=lambda: created))


def _stamp_of_a_new_process(boot_time: list[float]) -> float:
    """The stamp of a process object built now, as every caller builds one per read.

    psutil on Linux reports the boot time plus the ticks since boot, and the object keeps what it first reported.
    """
    return start_stamp(_started_at(boot_time[0] + _TICKS_SINCE_BOOT))


def test_two_reads_of_a_live_process_agree() -> None:
    assert start_stamp(psutil.Process()) == pytest.approx(start_stamp(psutil.Process()), abs=1.0)


def test_a_clock_step_does_not_move_the_stamp_where_start_times_follow_the_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boot_time = [_BOOT_TIME]
    monkeypatch.setattr(psutil, "boot_time", lambda: boot_time[0])
    monkeypatch.setattr(process_start, "_START_TIMES_FOLLOW_WALL_CLOCK", True)
    before = _stamp_of_a_new_process(boot_time)

    boot_time[0] += 600.0  # an NTP step, or a VM resumed with a corrected clock

    assert before == pytest.approx(_TICKS_SINCE_BOOT)
    assert _stamp_of_a_new_process(boot_time) == pytest.approx(before)


def test_the_start_time_is_returned_as_it_is_where_it_is_a_fixed_instant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(psutil, "boot_time", lambda: _BOOT_TIME)
    monkeypatch.setattr(process_start, "_START_TIMES_FOLLOW_WALL_CLOCK", False)

    assert start_stamp(_started_at(1234.5)) == 1234.5


@pytest.mark.parametrize("follows_wall_clock", [True, False])
def test_a_process_that_started_an_hour_later_has_another_stamp(
    monkeypatch: pytest.MonkeyPatch, follows_wall_clock: bool
) -> None:
    monkeypatch.setattr(psutil, "boot_time", lambda: _BOOT_TIME)
    monkeypatch.setattr(process_start, "_START_TIMES_FOLLOW_WALL_CLOCK", follows_wall_clock)
    holder = _started_at(_BOOT_TIME + _TICKS_SINCE_BOOT)
    taker = _started_at(_BOOT_TIME + _TICKS_SINCE_BOOT + 3600.0)

    assert abs(start_stamp(taker) - start_stamp(holder)) > 1.0


def test_the_module_imports_without_psutil() -> None:
    """``owner_stamp_env`` promises an empty stamp without psutil, so importing the stamp source must not need it."""
    name = process_start.__name__
    with patch.dict(sys.modules, {"psutil": None}):
        sys.modules.pop(name, None)
        importlib.import_module(name)
