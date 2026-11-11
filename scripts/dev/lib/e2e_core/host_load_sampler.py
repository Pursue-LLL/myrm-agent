"""Host load sampler — one aggregate snapshot of machine pressure and per-role process load.

[INPUT]
- host_resource_governor.collect_host_pressure_snapshot (load average, CPU count, free memory)
- ``host_statistics`` cumulative CPU ticks (ctypes, no subprocess)
- ``ps -axo pid,rss,time,etime,command`` (one subprocess per sample)

[OUTPUT]
- LoadSampler.sample() -> LoadSample | None (None while priming)
- classify_role(command) -> role label

[POS]
Read-only observer behind host_load_recorder. A sample holds counts, CPU cores and RSS per
role label and never a command line, so persisted rows are safe to share.
Processes that start and exit between two samples are invisible per role; their CPU shows up
as ``unattributed_cores`` (machine-busy cores minus the sum over visible processes).
"""

from __future__ import annotations

import ctypes
import functools
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypedDict

from e2e_core.host_resource_governor import collect_host_pressure_snapshot

YOUNG_PROCESS_SEC: Final = 120
MAX_SAMPLE_GAP_SEC: Final = 120.0
PS_TIMEOUT_SEC: Final = 20.0
_NEW_PROCESS_SLACK_SEC: Final = 5
_PS_ARGV: Final = ("/bin/ps", "-axo", "pid=,rss=,time=,etime=,command=")
_PS_ROW: Final = re.compile(r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(.*)")
_HOST_CPU_LOAD_INFO: Final = 3
_TICK_MODULUS: Final = 1 << 32

_CHROME_MARKERS: Final = (
    "/Google Chrome.app/",
    "Google Chrome Helper",
    "/Chromium.app/",
    "chrome-headless-shell",
)
_SYSTEM_PREFIXES: Final = (
    "/System/",
    "/usr/libexec/",
    "/usr/sbin/",
    "/usr/bin/",
    "/sbin/",
    "/bin/",
    "kernel_task",
)
_PYTEST: Final = re.compile(
    r"(?:^|\s)-m\s+pytest(?:\s|$)|run_pytest_safe\.py|/bin/pytest(?:\s|$)"
)
_NEXT: Final = re.compile(
    r"next-server|/next/dist/bin/next|(?:^|\s)next\s+(?:dev|start|build)(?:\s|$)"
)
_CURSOR: Final = re.compile(r"/Cursor[^/]*\.app/|/\.cursor[^/]*/|cursor-agent")


class RoleStat(TypedDict):
    """Per-role aggregate: process count, busy cores, RSS and young-process count."""

    n: int
    cpu: float
    rss_mb: int
    young: int


class LoadSample(TypedDict):
    ts: float
    dt: float
    load1: float
    load5: float
    ncpu: int
    mem_avail_mb: int
    cpu_user: float
    cpu_sys: float
    cpu_idle: float
    procs: int
    young: int
    unattributed_cores: float
    roles: dict[str, RoleStat]


@dataclass(frozen=True, slots=True)
class ProcRow:
    pid: int
    rss_kb: int
    cpu_sec: float
    age_sec: int
    command: str


@dataclass(frozen=True, slots=True)
class CpuTicks:
    user: int
    system: int
    idle: int
    nice: int


@dataclass(slots=True)
class _RoleAccumulator:
    n: int = 0
    cpu_sec: float = 0.0
    rss_kb: int = 0
    young: int = 0


def parse_cpu_time(text: str) -> float:
    """Parse ps ``time`` (``M+:SS.cc``; hours form ``H:MM:SS`` also accepted) into seconds."""
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def parse_elapsed(text: str) -> int:
    """Parse ps ``etime`` (``[[D-]HH:]MM:SS``) into whole seconds."""
    days, _, clock = text.rpartition("-")
    seconds = 0
    for part in clock.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds + (int(days) * 86400 if days else 0)


def parse_ps_output(text: str) -> list[ProcRow]:
    rows: list[ProcRow] = []
    for line in text.splitlines():
        match = _PS_ROW.fullmatch(line)
        if match is None:
            continue
        try:
            rows.append(
                ProcRow(
                    pid=int(match[1]),
                    rss_kb=int(match[2]),
                    cpu_sec=parse_cpu_time(match[3]),
                    age_sec=parse_elapsed(match[4]),
                    command=match[5],
                )
            )
        except ValueError:
            continue
    return rows


def classify_role(command: str) -> str:
    """Map a command line to a stable role label; Chrome is split by Myrm profile."""
    if any(marker in command for marker in _CHROME_MARKERS):
        if "/Myrm/ChromeAgent" in command:
            return (
                "chrome_agent_ext"
                if "--extension-process" in command
                else "chrome_agent"
            )
        return "chrome_e2e" if "/Myrm/ChromeE2E" in command else "chrome_other"
    if _PYTEST.search(command):
        return "pytest"
    if _NEXT.search(command):
        return "next_server"
    if _CURSOR.search(command):
        return "cursor"
    tokens = command.split(None, 1)
    executable = os.path.basename(tokens[0]) if tokens else ""
    if executable == "node":
        return "node"
    if executable.lower().startswith("python"):
        return "python"
    if command.startswith(_SYSTEM_PREFIXES):
        return "system"
    return "other"


@functools.cache
def _libsystem() -> ctypes.CDLL:
    return ctypes.CDLL("/usr/lib/libSystem.B.dylib")


def read_cpu_ticks() -> CpuTicks | None:
    """Cumulative (user, system, idle, nice) ticks; None off macOS or on kernel error."""
    if sys.platform != "darwin":
        return None
    libsystem = _libsystem()
    ticks = (ctypes.c_uint32 * 4)()
    count = ctypes.c_uint32(4)
    status = libsystem.host_statistics(
        libsystem.mach_host_self(), _HOST_CPU_LOAD_INFO, ticks, ctypes.byref(count)
    )
    if status != 0:
        return None
    return CpuTicks(user=ticks[0], system=ticks[1], idle=ticks[2], nice=ticks[3])


def cpu_split(previous: CpuTicks, current: CpuTicks) -> tuple[float, float, float]:
    """Return (user+nice, system, idle) percent between two tick readings (32-bit wrap safe)."""
    user = (current.user - previous.user) % _TICK_MODULUS
    nice = (current.nice - previous.nice) % _TICK_MODULUS
    system = (current.system - previous.system) % _TICK_MODULUS
    idle = (current.idle - previous.idle) % _TICK_MODULUS
    total = user + nice + system + idle
    if total == 0:
        return 0.0, 0.0, 0.0
    return 100 * (user + nice) / total, 100 * system / total, 100 * idle / total


def capture_processes() -> list[ProcRow]:
    """Run ``ps`` once and parse every row except the ``ps`` child itself."""
    completed = subprocess.run(
        _PS_ARGV,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=PS_TIMEOUT_SEC,
        check=True,
    )
    own_command = f"{_PS_ARGV[0]} -axo"
    return [
        row
        for row in parse_ps_output(completed.stdout)
        if not row.command.startswith(own_command)
    ]


def _cpu_delta(
    row: ProcRow, previous: Mapping[int, tuple[float, int]], dt: float
) -> float:
    """CPU seconds a process consumed since the previous sample."""
    before = previous.get(row.pid)
    if before is not None and row.cpu_sec >= before[0] and row.age_sec >= before[1]:
        return row.cpu_sec - before[0]
    # First sighting or recycled pid: its whole history belongs to this interval only if it
    # started inside it; an older unseen process cannot be attributed.
    return row.cpu_sec if row.age_sec <= dt + _NEW_PROCESS_SLACK_SEC else 0.0


def aggregate_roles(
    rows: Sequence[ProcRow], previous: Mapping[int, tuple[float, int]], dt: float
) -> dict[str, RoleStat]:
    accumulators: dict[str, _RoleAccumulator] = {}
    for row in rows:
        accumulator = accumulators.setdefault(
            classify_role(row.command), _RoleAccumulator()
        )
        accumulator.n += 1
        accumulator.cpu_sec += _cpu_delta(row, previous, dt)
        accumulator.rss_kb += row.rss_kb
        accumulator.young += int(row.age_sec <= YOUNG_PROCESS_SEC)
    return {
        role: RoleStat(
            n=acc.n,
            cpu=round(acc.cpu_sec / dt, 3),
            rss_mb=acc.rss_kb // 1024,
            young=acc.young,
        )
        for role, acc in sorted(accumulators.items())
    }


class LoadSampler:
    """Stateful sampler: CPU shares need the previous tick and per-pid CPU seconds."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._ticks: CpuTicks | None = None
        self._cpu_by_pid: dict[int, tuple[float, int]] = {}
        self._at: float | None = None

    def sample(self) -> LoadSample | None:
        """Take one sample; the first call only primes state and returns None."""
        now = self._clock()
        rows = capture_processes()
        ticks = read_cpu_ticks()
        previous_ticks, previous_cpu, previous_at = (
            self._ticks,
            self._cpu_by_pid,
            self._at,
        )
        self._ticks, self._at = ticks, now
        self._cpu_by_pid = {row.pid: (row.cpu_sec, row.age_sec) for row in rows}
        if (
            previous_ticks is None
            or previous_at is None
            or ticks is None
            or now <= previous_at
        ):
            return None
        dt = now - previous_at
        if dt > MAX_SAMPLE_GAP_SEC:
            # Slept or stalled: CPU ticks only advance while awake, so per-role cores over the
            # wall-clock gap would be silently wrong. State is already refreshed for the next tick.
            return None
        user, system, idle = cpu_split(previous_ticks, ticks)
        pressure = collect_host_pressure_snapshot(now=now)
        roles = aggregate_roles(rows, previous_cpu, dt)
        busy_cores = (user + system) / 100 * pressure.cpu_count
        attributed_cores = sum(stat["cpu"] for stat in roles.values())
        return LoadSample(
            ts=round(now, 1),
            dt=round(dt, 1),
            load1=round(pressure.load_avg_1m, 2),
            load5=round(pressure.load_avg_5m, 2),
            ncpu=pressure.cpu_count,
            mem_avail_mb=pressure.memory_available_bytes >> 20,
            cpu_user=round(user, 1),
            cpu_sys=round(system, 1),
            cpu_idle=round(idle, 1),
            procs=len(rows),
            young=sum(stat["young"] for stat in roles.values()),
            unattributed_cores=round(max(0.0, busy_cores - attributed_cores), 2),
            roles=roles,
        )
