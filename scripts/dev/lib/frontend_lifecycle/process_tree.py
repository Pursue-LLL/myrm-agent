"""Process-tree evidence for the shared frontend restart gate.

[INPUT]
  ps(1) / lsof(8): per-process CPU time, elapsed time, parent links, LISTEN owners

[OUTPUT]
  ProcSample: one process row (pid, ppid, cpu_sec, age_sec)
  parse_ps_duration / snapshot / descendants / listener_pids / read_pid_file / run_command

[POS]
  Read-only observation primitives. A restart decision needs proof that the Next dev
  server is making progress (CPU time of its whole process tree), which no HTTP probe
  can provide while the server is busy compiling.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

CommandRunner = Callable[[Sequence[str]], str]
_COMMAND_TIMEOUT_SEC = 10.0


@dataclass(frozen=True)
class ProcSample:
    pid: int
    ppid: int
    cpu_sec: float
    age_sec: float


def run_command(argv: Sequence[str]) -> str:
    """Return stdout of a read-only command; empty string when it cannot run."""
    try:
        result = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout


def parse_ps_duration(raw: str) -> float:
    """Parse ps ``[[DD-]HH:]MM:SS[.ss]`` (macOS ``time=`` / Linux ``etime=``) to seconds."""
    text = raw.strip()
    days = 0
    if "-" in text:
        day_part, text = text.split("-", 1)
        days = int(day_part)
    parts = text.split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"unsupported ps duration: {raw!r}")
    seconds = float(parts[-1])
    minutes = int(parts[-2]) if len(parts) >= 2 else 0
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def snapshot(runner: CommandRunner = run_command) -> dict[int, ProcSample]:
    """All processes keyed by pid (one ps call, tolerant of unparsable rows)."""
    samples: dict[int, ProcSample] = {}
    for line in runner(["ps", "-axo", "pid=,ppid=,time=,etime="]).splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        try:
            pid, ppid = int(fields[0]), int(fields[1])
            cpu_sec, age_sec = (
                parse_ps_duration(fields[2]),
                parse_ps_duration(fields[3]),
            )
        except ValueError:
            continue
        samples[pid] = ProcSample(pid=pid, ppid=ppid, cpu_sec=cpu_sec, age_sec=age_sec)
    return samples


def descendants(samples: dict[int, ProcSample], roots: Iterable[int]) -> set[int]:
    """Roots that are alive plus every transitive child."""
    children: dict[int, list[int]] = {}
    for sample in samples.values():
        children.setdefault(sample.ppid, []).append(sample.pid)
    tree: set[int] = set()
    pending = [pid for pid in roots if pid in samples]
    while pending:
        pid = pending.pop()
        if pid in tree:
            continue
        tree.add(pid)
        pending.extend(children.get(pid, ()))
    return tree


def listener_pids(port: int, runner: CommandRunner = run_command) -> tuple[int, ...]:
    """PIDs holding a LISTEN socket on ``port`` (clients are never included)."""
    out = runner(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    return tuple(sorted({int(token) for token in out.split() if token.isdigit()}))


def read_pid_file(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None
