#!/usr/bin/env python3
"""Run a command; when it goes silent, record where it is stuck before killing it.

A test run that stops printing for longer than any single test may run (pytest-timeout) is stuck
outside the tests' own supervision: the master or a worker is blocked where no per-test timer is
armed, or inside a call a signal cannot interrupt. The CI job limit would cancel such a run without
leaving a trace, so this guard keeps the evidence itself. It tees the command's output to a log,
and once the command has been silent for ``--stall-seconds`` it

1. lists every process in the command's tree with each thread's state and kernel wait channel,
2. asks each Python process for every thread's stack (``SIGUSR1``; ``tests/conftest.py`` registers
   ``faulthandler`` for it in the pytest master and in every xdist worker),
3. kills the process group and exits with ``STALL_EXIT_CODE``.

While the command runs, one ``[ci-sample]`` line per ``--sample-seconds`` records load, memory and
pressure, so a slow runner is visible in the log of a run that finished.

Run::

    python3 scripts/ci_stall_guard.py --log /tmp/unit.log -- uv run --no-sync pytest -n 2 tests/

Exit codes:
    the command's own code when it finishes (128 + signal when a signal ended it)
    124  the command went silent and was killed
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

STALL_EXIT_CODE = 124
_DUMP_GRACE_SECONDS = 1.0
_READ_CHUNK = 65536
_PROC = Path("/proc")


class _Output:
    """Tee to the console and the log. The time of the command's last write is the stall clock."""

    def __init__(self, console: BinaryIO, log: BinaryIO) -> None:
        self._sinks = (console, log)
        self._lock = threading.Lock()
        self._at_line_start = True
        self.last_write = time.monotonic()

    def from_command(self, data: bytes) -> None:
        with self._lock:
            self._write(data)
            self._at_line_start = data.endswith(b"\n")
            self.last_write = time.monotonic()

    def from_guard(self, text: str) -> None:
        """Guard diagnostics must not reset the stall clock, or sampling would hide the stall.

        pytest -v leaves a line open while a test runs, so a diagnostic first ends that line.
        """
        with self._lock:
            self._write(f"{'' if self._at_line_start else chr(10)}{text}\n".encode())
            self._at_line_start = True

    def _write(self, data: bytes) -> None:
        for sink in self._sinks:
            sink.write(data)
            sink.flush()


def _pump(stream: BinaryIO, output: _Output) -> None:
    # A raw read hands over whatever has arrived, so a progress mark without a newline still counts as output.
    while data := os.read(stream.fileno(), _READ_CHUNK):
        output.from_command(data)


def _process_table() -> dict[int, tuple[int, str]]:
    """Map pid to (parent pid, executable) for every process; empty when ``ps`` is unavailable."""
    try:
        listing = subprocess.run(["ps", "-axo", "pid=,ppid=,comm="], capture_output=True, text=True, check=False).stdout
    except OSError:
        return {}
    table: dict[int, tuple[int, str]] = {}
    for row in listing.splitlines():
        fields = row.split(None, 2)
        if len(fields) == 3:
            table[int(fields[0])] = (int(fields[1]), fields[2])
    return table


def _descendants(root: int, table: dict[int, tuple[int, str]]) -> list[int]:
    children: dict[int, list[int]] = {}
    for pid, (parent, _) in table.items():
        children.setdefault(parent, []).append(pid)
    found: list[int] = []
    pending = [root]
    while pending:
        for child in children.get(pending.pop(), []):
            found.append(child)
            pending.append(child)
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _status_kb(pid: int, field: str) -> int:
    for line in _read(_PROC / str(pid) / "status").splitlines():
        if line.startswith(f"{field}:"):
            return int(line.split()[1])
    return 0


def _thread_rows(pid: int) -> list[str]:
    """State and kernel wait channel of each thread; empty without ``/proc``."""
    rows: list[str] = []
    for task in sorted((_PROC / str(pid) / "task").glob("*")):
        # The command name sits in parentheses and may itself contain spaces, so the state follows the last ")".
        fields_after_name = _read(task / "stat").rpartition(")")[2].split()
        if not fields_after_name:
            continue
        wchan = _read(task / "wchan").strip() or "-"
        rows.append(
            f"    tid={task.name} state={fields_after_name[0]} wchan={wchan} comm={_read(task / 'comm').strip()}"
        )
    return rows


def _meminfo_mb() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in _read(_PROC / "meminfo").splitlines():
        name, _, rest = line.partition(":")
        if name in {"MemAvailable", "SwapTotal", "SwapFree"}:
            values[name] = int(rest.split()[0]) // 1024
    return values


def _pressure(resource: str) -> str:
    """The ``some avg10`` share of time tasks were stalled on a resource (Linux PSI)."""
    for line in _read(_PROC / "pressure" / resource).splitlines():
        if line.startswith("some"):
            return dict(part.split("=") for part in line.split()[1:]).get("avg10", "?")
    return "?"


def _system_snapshot(tree: Sequence[int]) -> str:
    fields = [f"load={os.getloadavg()[0]:.1f}"]
    memory = _meminfo_mb()
    if memory:
        fields.append(f"mem_available_mb={memory.get('MemAvailable', '?')}")
        fields.append(f"swap_used_mb={memory.get('SwapTotal', 0) - memory.get('SwapFree', 0)}")
        fields.append(f"tree_rss_mb={sum(_status_kb(pid, 'VmRSS') for pid in tree) // 1024}")
        fields.extend(f"psi_{name}={_pressure(name)}" for name in ("cpu", "memory", "io"))
    return " ".join(fields)


def _is_python(executable: str) -> bool:
    return Path(executable).name.startswith("python")


def _report_stall(root: int, output: _Output, silent_for: float) -> None:
    table = _process_table()
    tree = [pid for pid in (root, *_descendants(root, table)) if pid in table]
    output.from_guard(f"[ci-stall] no output for {silent_for:.0f}s; processes in the tree: {len(tree)}")
    output.from_guard(f"[ci-stall] system {_system_snapshot(tree)}")
    for pid in tree:
        output.from_guard(f"[ci-stall] pid={pid} ppid={table[pid][0]} comm={table[pid][1]} threads:")
        for row in _thread_rows(pid):
            output.from_guard(row)
    for pid in tree:
        if not _is_python(table[pid][1]):
            continue
        output.from_guard(f"[ci-stall] stacks of pid={pid}")
        try:
            os.kill(pid, signal.SIGUSR1)
        except ProcessLookupError:
            continue
        time.sleep(_DUMP_GRACE_SECONDS)
    output.from_guard("[ci-stall] killing the process group")


def _kill_group(child: subprocess.Popen[bytes]) -> None:
    # macOS answers EPERM, not ESRCH, for a group that only has zombies left.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def run_guarded(
    command: Sequence[str],
    *,
    stall_seconds: float,
    sample_seconds: float,
    log_path: Path,
    console: BinaryIO,
) -> int:
    """Run ``command`` and return its exit code, or ``STALL_EXIT_CODE`` when it went silent and was killed."""
    started = time.monotonic()
    with log_path.open("wb") as log:
        output = _Output(console, log)
        child = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        assert child.stdout is not None
        reader = threading.Thread(target=_pump, args=(child.stdout, output), daemon=True)
        reader.start()
        next_sample = started + sample_seconds
        try:
            while child.poll() is None:
                time.sleep(0.2)
                now = time.monotonic()
                if now - output.last_write > stall_seconds:
                    _report_stall(child.pid, output, now - output.last_write)
                    return STALL_EXIT_CODE
                if sample_seconds > 0 and now >= next_sample:
                    tree = [child.pid, *_descendants(child.pid, _process_table())]
                    output.from_guard(f"[ci-sample] +{now - started:.0f}s {_system_snapshot(tree)}")
                    next_sample = now + sample_seconds
        finally:
            _kill_group(child)
            reader.join(timeout=5)
    return child.returncode if child.returncode >= 0 else 128 - child.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stall-seconds", type=float, default=600.0, help="silence that counts as a stall")
    parser.add_argument(
        "--sample-seconds", type=float, default=60.0, help="seconds between [ci-sample] lines; 0 = none"
    )
    parser.add_argument("--log", type=Path, required=True, help="file that receives a copy of the output")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the command to run")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")
    # A runner cancel sends SIGTERM; unwinding through ``run_guarded`` kills the command's process group.
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(128 + signal.SIGTERM))
    return run_guarded(
        command,
        stall_seconds=args.stall_seconds,
        sample_seconds=args.sample_seconds,
        log_path=args.log,
        console=sys.stdout.buffer,
    )


if __name__ == "__main__":
    sys.exit(main())
