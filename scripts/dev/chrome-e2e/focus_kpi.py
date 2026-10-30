#!/usr/bin/env python3
"""Front-process switch KPI for the Myrm E2E harness (macOS only).

The harness promise is "never disturb the user's work", so the only honest ruler is the macOS foreground app
itself. Every switch is read from the unified log (event level, no polling gaps) together with the process that
asked for it and how long the user had been idle. KPI = switches that happen while the user is idle: "I did
nothing, yet the front app changed".

    focus_kpi.py watch --duration 600 [--idle-seconds 5] [--fail-on-caller "System Events"]

`--fail-on-caller` is stricter than the idle KPI: a switch requested by the named process is a defect even while
the user is typing, which is when losing the front hurts most.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

# A SetFrontProcess call is blamed for a switch logged within this window after it.
CALLER_WINDOW_S = 0.15
# Switches without a SetFrontProcess caller come from user clicks, Cmd+Tab or the system.
NO_CALLER = "none(user/system)"
UNKNOWN_APP = "unknown"

_LOG_PREDICATE = (
    '(process == "WindowServer" AND (eventMessage CONTAINS "Making <private>"'
    ' OR eventMessage CONTAINS "Deferring events from frontmost"))'
    ' OR eventMessage CONTAINS "SetFrontProcess: asn"'
)
_TS = r"(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})"
_CALL_RE = re.compile(
    _TS
    + r"\s+\S+\s+(?P<proc>.+?)\[\d+:[0-9a-f]+\].*SetFrontProcess: asn=0x0-(?P<asn>0x[0-9a-f]+)"
)
_MAKE_RE = re.compile(
    _TS
    + r"\s+\S+\s+WindowServer\[\d+:[0-9a-f]+\].*Making <private> 0x0-(?P<asn>0x[0-9a-f]+) the front process"
)
_DEFER_RE = re.compile(
    r"frontmost process PSN 0x0-(?P<asn>0x[0-9a-f]+) \((?P<app>.+?)\) -> <pid: (?P<pid>\d+)>"
)
_HID_IDLE_RE = re.compile(r'"HIDIdleTime" = (\d+)')


@dataclass(frozen=True)
class FrontSwitch:
    """One change of the macOS front process."""

    time: datetime
    app: str
    pid: int
    caller: str
    idle_s: float

    def is_idle(self, threshold_s: float) -> bool:
        return self.idle_s >= threshold_s


@dataclass(frozen=True)
class KpiSummary:
    total: int
    idle: int
    by_caller: dict[str, int]
    idle_by_caller: dict[str, int]
    idle_by_app: dict[str, int]


def read_hid_idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input; -1.0 when unreadable (treated as not idle)."""
    out = subprocess.run(
        ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    match = _HID_IDLE_RE.search(out)
    return int(match.group(1)) / 1e9 if match else -1.0


def _parse_ts(raw: str) -> datetime:
    # The unified log prints local wall-clock time; astimezone() on a naive value attaches the local zone.
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f").astimezone()


class FrontSwitchParser:
    """Incremental parser: feed `log stream --style compact` lines, receive completed switches.

    A switch spans two WindowServer lines: "Making <asn> the front process" (carries the time) and the
    "Deferring events ... (<app>) -> <pid: N>" line that names the app. The idle time is sampled at the first one.
    """

    def __init__(self, idle_reader: Callable[[], float]) -> None:
        self._idle_reader = idle_reader
        self._last_call: tuple[datetime, str] | None = None
        self._pending: dict[str, tuple[datetime, str, float]] = {}

    def feed(self, line: str) -> list[FrontSwitch]:
        call = _CALL_RE.match(line)
        if call:
            self._last_call = (_parse_ts(call["ts"]), call["proc"])
            return []
        make = _MAKE_RE.match(line)
        if make:
            completed = self.flush()
            when = _parse_ts(make["ts"])
            self._pending[make["asn"]] = (
                when,
                self._caller_at(when),
                self._idle_reader(),
            )
            return completed
        defer = _DEFER_RE.search(line)
        if defer and defer["asn"] in self._pending:
            when, caller, idle_s = self._pending.pop(defer["asn"])
            return [FrontSwitch(when, defer["app"], int(defer["pid"]), caller, idle_s)]
        return []

    def flush(self) -> list[FrontSwitch]:
        """Close switches whose app name never arrived, so none is silently dropped."""
        unresolved = [
            FrontSwitch(when, UNKNOWN_APP, -1, caller, idle_s)
            for when, caller, idle_s in self._pending.values()
        ]
        self._pending.clear()
        return sorted(unresolved, key=lambda switch: switch.time)

    def _caller_at(self, when: datetime) -> str:
        if self._last_call is None:
            return NO_CALLER
        call_time, caller = self._last_call
        return (
            caller
            if 0 <= (when - call_time).total_seconds() <= CALLER_WINDOW_S
            else NO_CALLER
        )


def summarize(switches: Iterable[FrontSwitch], idle_threshold_s: float) -> KpiSummary:
    records = list(switches)
    idle = [switch for switch in records if switch.is_idle(idle_threshold_s)]
    return KpiSummary(
        total=len(records),
        idle=len(idle),
        by_caller=dict(Counter(switch.caller for switch in records)),
        idle_by_caller=dict(Counter(switch.caller for switch in idle)),
        idle_by_app=dict(Counter(switch.app for switch in idle)),
    )


def watch(
    duration_s: float, idle_threshold_s: float, emit: Callable[[str], None]
) -> list[FrontSwitch]:
    """Stream the unified log for `duration_s` seconds and report every front switch as it happens."""
    stream = subprocess.Popen(
        ["/usr/bin/log", "stream", "--style", "compact", "--predicate", _LOG_PREDICATE],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    # readline() blocks while the log is quiet, so the deadline is enforced by ending the stream itself.
    expired = threading.Event()

    def expire() -> None:
        expired.set()  # set before terminating, so the EOF that follows is never mistaken for a dead stream
        stream.terminate()

    deadline = threading.Timer(duration_s, expire)
    deadline.start()
    parser = FrontSwitchParser(read_hid_idle_seconds)
    collected: list[FrontSwitch] = []

    def report(switches: list[FrontSwitch]) -> None:
        for switch in switches:
            collected.append(switch)
            flag = "  <<< IDLE SWITCH" if switch.is_idle(idle_threshold_s) else ""
            emit(
                f"{switch.time:%H:%M:%S} -> {switch.app}({switch.pid}) "
                f"caller={switch.caller} idle={switch.idle_s:.1f}s{flag}"
            )

    try:
        for line in stream.stdout or ():
            report(parser.feed(line))
        # EOF before the deadline means the log stream died: reporting "0 switches" then would be a false all-clear.
        if not expired.is_set():
            raise RuntimeError("log stream ended before the observation window elapsed")
    finally:
        deadline.cancel()
        stream.terminate()
        stream.wait()
        report(parser.flush())
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Myrm E2E front-process switch KPI (macOS)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    watch_parser = sub.add_parser(
        "watch", help="stream front switches and print the idle-switch KPI"
    )
    watch_parser.add_argument(
        "--duration", type=float, default=600.0, help="seconds to observe"
    )
    watch_parser.add_argument(
        "--idle-seconds",
        type=float,
        default=5.0,
        help="user idle time that counts as 'did nothing'",
    )
    watch_parser.add_argument(
        "--fail-on-caller",
        action="append",
        default=[],
        metavar="CALLER",
        help="exit 1 when this caller requested any front switch (repeatable), e.g. 'System Events'",
    )
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("focus_kpi: macOS only", file=sys.stderr)
        return 2

    switches = watch(
        args.duration, args.idle_seconds, lambda line: print(line, flush=True)
    )
    summary = summarize(switches, args.idle_seconds)
    print(
        f"SUMMARY total_switches={summary.total} idle_switches(>={args.idle_seconds:g}s)={summary.idle}"
    )
    print(f"idle switches by caller: {summary.idle_by_caller}")
    print(f"idle switches by app: {summary.idle_by_app}")
    if summary.total == 0:
        # A silent blind spot would read as a clean pass, so an empty window is called out explicitly.
        print(
            "WARNING: no front switch observed at all; confirm the log stream delivers events",
            file=sys.stderr,
        )
    # A SetFrontProcess call by the forbidden caller is the culprit whether or not the user happened to be busy.
    offenders = {
        caller: n
        for caller, n in summary.by_caller.items()
        if caller in args.fail_on_caller
    }
    if offenders:
        print(
            f"FOCUS_KPI_FAIL: front switches requested by {offenders}", file=sys.stderr
        )
        return 1
    print("FOCUS_KPI_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
