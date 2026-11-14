"""Readable view of stored hotspot captures.

[INPUT]
- Hotspot rows from host_load_store.read_hotspots

[OUTPUT]
- render_hotspot(hotspot) -> str: one capture
- render_hotspots(hotspots, hours=..., limit=...) -> str: the newest captures

[POS]
Answers "which process, started by what, was behind that spike" from a stored capture alone.
Each capture lists its processes under the rankings they made (CPU, footprint, running
threads) with the parent chain that started them, so a pytest-xdist worker reads as the test
run that owns it. Sizes print in binary units (MiB, GiB), the unit the stored ``*_mb`` fields
count in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Final

from e2e_core.host_hotspot_capture import HotProc, Hotspot

_SHOWN_PER_SECTION: Final = 5
_MIB_PER_GIB: Final = 1024
_PARENT_LEVELS_SHOWN: Final = 2

_Metric = Callable[[HotProc], float]
_SECTIONS: Final[tuple[tuple[str, str, _Metric], ...]] = (
    ("cpu", "by CPU", lambda proc: proc["cpu"]),
    ("mem", "by footprint", lambda proc: proc["foot_mb"]),
    ("threads", "by running threads", lambda proc: proc.get("running", 0)),
)


def _stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def _size(mib: int) -> str:
    if mib >= _MIB_PER_GIB:
        return f"{mib / _MIB_PER_GIB:.1f} GiB"
    return f"{mib} MiB"


def _host_line(hotspot: Hotspot) -> str | None:
    parts: list[str] = []
    if "load1" in hotspot:
        parts.append(f"load1 {hotspot['load1']:.1f}")
    if "cpu_idle" in hotspot:
        parts.append(f"idle {hotspot['cpu_idle']:.0f}%")
    if "mem_avail_mb" in hotspot:
        parts.append(f"free {_size(hotspot['mem_avail_mb'])}")
    if "pressure" in hotspot:
        parts.append(f"memory pressure level {hotspot['pressure']}")
    return "host: " + ", ".join(parts) if parts else None


def _proc_lines(proc: HotProc, parents: dict[str, str]) -> list[str]:
    threads = ""
    if "threads" in proc:
        threads = f"  threads {proc['threads']} (running {proc.get('running', 0)})"
    head = f"    {proc['role']:<11}{proc['cpu']:6.2f}c  {_size(proc['foot_mb']):>9}"
    lines = [f"{head}{threads}  pid {proc['pid']}  {proc['cmd']}"]
    owners = [
        parents[str(pid)]
        for pid in proc["up"][:_PARENT_LEVELS_SHOWN]
        if str(pid) in parents
    ]
    if owners:
        lines.append("        started by: " + " <- ".join(owners))
    return lines


def render_hotspot(hotspot: Hotspot) -> str:
    lines = [f"{_stamp(hotspot['ts'])}  {', '.join(hotspot['reasons'])}"]
    host = _host_line(hotspot)
    if host is not None:
        lines.append(f"  {host}")
    for key, title, metric in _SECTIONS:
        members = [proc for proc in hotspot["procs"] if key in proc["why"]]
        if not members:
            continue
        lines.append(f"  {title}:")
        members.sort(key=lambda proc: (-metric(proc), proc["pid"]))
        for proc in members[:_SHOWN_PER_SECTION]:
            lines.extend(_proc_lines(proc, hotspot["parents"]))
    return "\n".join(lines)


def render_hotspots(
    hotspots: Sequence[Hotspot], *, hours: float | None, limit: int
) -> str:
    window = "" if hours is None else f" in the last {hours:g}h"
    if not hotspots:
        return (
            f"No hotspot captures{window} (they are written only when a trigger fires;"
            " `snapshot` takes one now)."
        )
    newest = sorted(hotspots, key=lambda item: item["ts"], reverse=True)[:limit]
    blocks = [f"Hotspot captures{window}: {len(hotspots)}, newest {len(newest)} shown"]
    blocks.extend(render_hotspot(item) for item in newest)
    return "\n\n".join(blocks)
