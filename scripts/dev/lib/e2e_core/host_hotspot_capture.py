"""Per-process hotspot capture: who is burning CPU, holding memory or running many threads.

[INPUT]
- ``/bin/ps -axo pid=,ppid=,%cpu=,rss=,etime=,command=`` (one subprocess per capture, capped
  at PS_TIMEOUT_SEC)
- proc_footprint.platform_reader (physical footprint per process)
- proc_threads.platform_thread_reader (thread totals and running threads per process)
- host_load_sampler.classify_role / parse_elapsed / PS_TIMEOUT_SEC (same role labels as the aggregate
  rows, ps elapsed-time parsing, the ps time cap)
- host_resource_governor.collect_host_pressure_snapshot and host_vm_stats.read_vm_snapshot (the host
  readings stored beside the processes)
- real_user_home.real_user_home (the home directory that prints as ``~``)
- command_redaction.redact_command (the only path a command line takes into a row)

[OUTPUT]
- Hotspot / HotProc: the stored row (host context, the hottest processes, their ancestors)
- HostContext: the host readings stored beside the processes
- parse_process_table(text) / capture_process_table() -> list[TableRow]: the parsed process table
- build_hotspot(...) -> Hotspot: pure, ranks a captured table
- capture_hotspot(ts, reasons, context) -> Hotspot: reads the machine, then builds
- host_context_now() -> HostContext
- TOP_PER_RANKING / MIN_CPU_PCT / MIN_FOOTPRINT_MB / MIN_RUNNING_THREADS / MAX_ANCESTOR_DEPTH /
  MAX_PARENTS / ARGUMENT_ROLES: the ranking limits and the roles that keep arguments

[POS]
The recorder's aggregate rows say which role was busy; this row says which process, with which
command, under which parent. It is captured only when a trigger fires (see
host_hotspot_trigger), so a calm machine pays nothing. A process enters the row when it ranks
in the top TOP_PER_RANKING by CPU (``%cpu`` is the kernel's recent-usage figure, the same window
the recorder samples), by footprint, or by running threads and reaches that ranking's floor
(MIN_CPU_PCT, MIN_FOOTPRINT_MB, MIN_RUNNING_THREADS); a process whose footprint cannot be read
counts at its RSS. Its ancestors (up to MAX_ANCESTOR_DEPTH levels, at most MAX_PARENTS labels per
row) are stored once in ``parents`` so pytest-xdist workers and Next dev children can be tied to
the test run or dev server that owns them. Commands go through command_redaction and only the
roles in ARGUMENT_ROLES keep arguments.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypedDict

from e2e_core.command_redaction import redact_command
from e2e_core.host_load_sampler import PS_TIMEOUT_SEC, classify_role, parse_elapsed
from e2e_core.host_resource_governor import collect_host_pressure_snapshot
from e2e_core.host_vm_stats import read_vm_snapshot
from e2e_core.proc_footprint import FootprintReader, platform_reader
from e2e_core.proc_threads import ThreadCounts, ThreadReader, platform_thread_reader
from e2e_core.real_user_home import real_user_home

TOP_PER_RANKING: Final = 8
MIN_CPU_PCT: Final = 25.0
MIN_FOOTPRINT_MB: Final = 512
MIN_RUNNING_THREADS: Final = 4
MAX_ANCESTOR_DEPTH: Final = 3
MAX_PARENTS: Final = 40
# Roles whose arguments identify the work (test targets, modules, ports); every other role
# keeps only its program name.
ARGUMENT_ROLES: Final = frozenset({"pytest", "python", "node", "next_server"})

_PS_ARGV: Final = ("/bin/ps", "-axo", "pid=,ppid=,%cpu=,rss=,etime=,command=")
_PS_ROW: Final = re.compile(
    r"\s*(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s+(\d+)\s+(\S+)\s+(.*)"
)


class _ProcCore(TypedDict):
    pid: int
    ppid: int
    role: str
    cpu: float
    foot_mb: int
    rss_mb: int
    age_s: int
    cmd: str
    why: list[str]
    up: list[int]


class HotProc(_ProcCore, total=False):
    """One listed process; ``cpu`` counts busy cores, ``why`` names the rankings it made.

    ``up`` lists its ancestors' pids, nearest first; ``Hotspot.parents`` labels them.
    ``threads`` and ``running`` are optional: the host may have no thread source, and
    processes of other users are unreadable.
    """

    threads: int
    running: int


class _HotspotCore(TypedDict):
    ts: float
    reasons: list[str]
    procs: list[HotProc]
    parents: dict[str, str]


class Hotspot(_HotspotCore, total=False):
    """One stored capture; ``parents`` maps an ancestor pid (as text) to its command label.

    The host fields are optional: a reading that failed is left out, never guessed.
    Every ``*_mb`` field counts mebibytes (2**20 bytes).
    """

    load1: float
    cpu_idle: float
    mem_avail_mb: int
    pressure: int


@dataclass(frozen=True, slots=True)
class HostContext:
    load1: float | None = None
    cpu_idle: float | None = None
    mem_avail_mb: int | None = None
    pressure: int | None = None


@dataclass(frozen=True, slots=True)
class TableRow:
    pid: int
    ppid: int
    cpu_pct: float
    rss_kb: int
    age_sec: int
    command: str


def parse_process_table(text: str) -> list[TableRow]:
    rows: list[TableRow] = []
    for line in text.splitlines():
        match = _PS_ROW.fullmatch(line)
        if match is None:
            continue
        try:
            rows.append(
                TableRow(
                    pid=int(match[1]),
                    ppid=int(match[2]),
                    cpu_pct=float(match[3]),
                    rss_kb=int(match[4]),
                    age_sec=parse_elapsed(match[5]),
                    command=match[6],
                )
            )
        except ValueError:
            continue
    return rows


def capture_process_table() -> list[TableRow]:
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
        for row in parse_process_table(completed.stdout)
        if not row.command.startswith(own_command)
    ]


def _read_footprints(
    pids: Iterable[int], read: FootprintReader | None
) -> dict[int, int]:
    if read is None:
        return {}
    sizes = ((pid, read(pid)) for pid in pids)
    return {pid: size for pid, size in sizes if size is not None}


def _read_threads(
    pids: Iterable[int], read: ThreadReader | None
) -> dict[int, ThreadCounts]:
    if read is None:
        return {}
    counts = ((pid, read(pid)) for pid in pids)
    return {pid: found for pid, found in counts if found is not None}


def _top(
    rows: Sequence[TableRow], score: Callable[[TableRow], float], floor: float
) -> list[TableRow]:
    ranked = sorted(rows, key=lambda row: (-score(row), row.pid))
    return [row for row in ranked[:TOP_PER_RANKING] if score(row) >= floor]


def _label(command: str, home: str) -> str:
    return redact_command(
        command, keep_arguments=classify_role(command) in ARGUMENT_ROLES, home=home
    )


def _ancestors(
    row: TableRow, by_pid: Mapping[int, TableRow], home: str
) -> list[tuple[int, str]]:
    """Up to MAX_ANCESTOR_DEPTH (pid, label) pairs above ``row``, nearest first, stopping at init."""
    found: list[tuple[int, str]] = []
    parent_pid = row.ppid
    for _ in range(MAX_ANCESTOR_DEPTH):
        parent = by_pid.get(parent_pid)
        if parent is None or parent.pid <= 1:
            break
        found.append((parent.pid, _label(parent.command, home)))
        parent_pid = parent.ppid
    return found


def build_hotspot(
    rows: Sequence[TableRow],
    footprints: Mapping[int, int],
    threads: Mapping[int, ThreadCounts],
    *,
    ts: float,
    reasons: Sequence[str],
    context: HostContext,
    home: str,
) -> Hotspot:
    """Rank a captured table into the hottest processes; ``footprints`` are bytes by pid."""
    foot_mb = {row.pid: footprints.get(row.pid, row.rss_kb << 10) >> 20 for row in rows}

    def running(row: TableRow) -> float:
        counts = threads.get(row.pid)
        return counts.running if counts is not None else 0

    rankings = (
        ("cpu", _top(rows, lambda row: row.cpu_pct, MIN_CPU_PCT)),
        ("mem", _top(rows, lambda row: foot_mb[row.pid], MIN_FOOTPRINT_MB)),
        ("threads", _top(rows, running, MIN_RUNNING_THREADS)),
    )
    chosen: dict[int, TableRow] = {}
    why: dict[int, list[str]] = {}
    for name, ranked in rankings:
        for row in ranked:
            chosen.setdefault(row.pid, row)
            why.setdefault(row.pid, []).append(name)

    by_pid = {row.pid: row for row in rows}
    procs: list[HotProc] = []
    parents: dict[str, str] = {}
    for pid, row in chosen.items():
        chain = _ancestors(row, by_pid, home)
        proc = HotProc(
            pid=pid,
            ppid=row.ppid,
            role=classify_role(row.command),
            cpu=round(row.cpu_pct / 100, 2),
            foot_mb=foot_mb[pid],
            rss_mb=row.rss_kb >> 10,
            age_s=row.age_sec,
            cmd=_label(row.command, home),
            why=why[pid],
            up=[parent_pid for parent_pid, _ in chain],
        )
        counts = threads.get(pid)
        if counts is not None:
            proc["threads"] = counts.total
            proc["running"] = counts.running
        procs.append(proc)
        for parent_pid, label in chain:
            if len(parents) < MAX_PARENTS:
                parents.setdefault(str(parent_pid), label)

    hotspot = Hotspot(
        ts=round(ts, 1), reasons=list(reasons), procs=procs, parents=parents
    )
    if context.load1 is not None:
        hotspot["load1"] = round(context.load1, 2)
    if context.cpu_idle is not None:
        hotspot["cpu_idle"] = round(context.cpu_idle, 1)
    if context.mem_avail_mb is not None:
        hotspot["mem_avail_mb"] = context.mem_avail_mb
    if context.pressure is not None:
        hotspot["pressure"] = context.pressure
    return hotspot


def capture_hotspot(
    ts: float,
    reasons: Sequence[str],
    context: HostContext,
    *,
    footprint_reader: FootprintReader | None = None,
    thread_reader: ThreadReader | None = None,
) -> Hotspot:
    """Read the process table, footprints and thread counts now, then rank them."""
    rows = capture_process_table()
    pids = [row.pid for row in rows]
    return build_hotspot(
        rows,
        _read_footprints(pids, footprint_reader or platform_reader()),
        _read_threads(pids, thread_reader or platform_thread_reader()),
        ts=ts,
        reasons=reasons,
        context=context,
        home=str(real_user_home()),
    )


def host_context_now() -> HostContext:
    """Load average, free memory and kernel pressure level as they are right now."""
    pressure = collect_host_pressure_snapshot()
    vm = read_vm_snapshot()
    return HostContext(
        load1=pressure.load_avg_1m,
        mem_avail_mb=pressure.memory_available_bytes >> 20,
        pressure=vm.pressure_level if vm is not None else None,
    )
