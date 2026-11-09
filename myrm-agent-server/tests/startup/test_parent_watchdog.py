"""Tests for the opt-in parent-exit watchdog used by probe and CI instances."""

import os
import signal
import time

from app.startup.parent_watchdog import start_parent_exit_watchdog


class _Parent:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def __call__(self) -> int:
        return self.pid


def test_signal_is_sent_after_the_parent_changes() -> None:
    parent = _Parent(4242)
    signalled: list[tuple[int, int]] = []

    thread = start_parent_exit_watchdog(
        interval_sec=0.01,
        getppid=parent,
        send_signal=lambda pid, sig: signalled.append((pid, sig)),
    )
    assert thread is not None
    parent.pid = 1
    thread.join(timeout=2.0)

    assert signalled == [(os.getpid(), signal.SIGTERM)]


def test_already_orphaned_exits_immediately() -> None:
    signalled: list[tuple[int, int]] = []

    thread = start_parent_exit_watchdog(
        getppid=lambda: 1,
        send_signal=lambda pid, sig: signalled.append((pid, sig)),
    )

    assert thread is None
    assert signalled == [(os.getpid(), signal.SIGTERM)]


def test_stable_parent_never_signals() -> None:
    signalled: list[tuple[int, int]] = []
    thread = start_parent_exit_watchdog(
        interval_sec=0.01,
        getppid=lambda: 4242,
        send_signal=lambda pid, sig: signalled.append((pid, sig)),
    )
    assert thread is not None
    time.sleep(0.05)
    assert signalled == []
    assert thread.is_alive()
