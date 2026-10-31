"""Physical-memory footprint of the Next dev server's process tree.

[INPUT]
  frontend_lifecycle.process_tree::snapshot / descendants (POS: read-only observation primitives
  over ps(1) parent links); libproc `proc_pid_rusage` on macOS, /proc/<pid>/status on Linux;
  dev_gate.contract::FRONTEND_FOOTPRINT_LIMIT_MB (POS: SSOT for the dev server's memory ceiling,
  overridden by MYRM_FRONTEND_FOOTPRINT_LIMIT_MB);
  frontend_lifecycle.policy::env_float (POS: positive-float env parsing with a default)

[OUTPUT]
  Measurement / measure() / limit_bytes() / platform_reader() / parse_vm_rss()

[POS]
  Evidence for the dev supervisor's memory guard (scripts/next-supervisor.ts). RSS is the wrong
  figure on macOS: one Bun-hosted Next server measured 2.7-8.5 GB RSS against ~22 GB
  phys_footprint, because compressed and swapped pages leave RSS yet still weigh on the machine.
  Linux has no such counter without root, so it sums RSS (shared pages counted once per process).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dev_gate.contract import FRONTEND_FOOTPRINT_LIMIT_MB

from frontend_lifecycle import process_tree
from frontend_lifecycle.policy import env_float

LIMIT_ENV = "MYRM_FRONTEND_FOOTPRINT_LIMIT_MB"
_BYTES_PER_MB = 1024 * 1024
# `struct rusage_info_v0` (sys/resource.h): uuid[16], then ri_user_time, ri_system_time,
# ri_pkg_idle_wkups, ri_interrupt_wkups, ri_pageins, ri_wired_size, ri_resident_size, and
# ri_phys_footprint as the eighth u64 field.
_RUSAGE_INFO_V0 = 0
_PHYS_FOOTPRINT_OFFSET = 16 + 7 * 8
_RUSAGE_BUFFER_BYTES = 512
_LIBPROC_FALLBACK = "/usr/lib/libproc.dylib"
_VM_RSS = re.compile(r"^VmRSS:\s+(\d+) kB$", re.MULTILINE)

# One process -> its footprint in bytes, or None when it is gone or unreadable.
FootprintReader = Callable[[int], int | None]


@dataclass(frozen=True)
class Measurement:
    root_pid: int
    pids: tuple[int, ...]
    footprint_bytes: int
    limit_bytes: int

    @property
    def exceeded(self) -> bool:
        return self.footprint_bytes > self.limit_bytes

    def render(self) -> str:
        return (
            f"FOOTPRINT pid={self.root_pid} procs={len(self.pids)} "
            f"mb={self.footprint_bytes // _BYTES_PER_MB} "
            f"limit_mb={self.limit_bytes // _BYTES_PER_MB}"
        )


def limit_bytes() -> int:
    mb = env_float(LIMIT_ENV, float(FRONTEND_FOOTPRINT_LIMIT_MB))
    return int(mb * _BYTES_PER_MB)


def _darwin_reader() -> FootprintReader | None:
    try:
        libproc = ctypes.CDLL(
            ctypes.util.find_library("proc") or _LIBPROC_FALLBACK, use_errno=True
        )
        proc_pid_rusage = libproc.proc_pid_rusage
    except (OSError, AttributeError):
        return None
    proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    proc_pid_rusage.restype = ctypes.c_int

    def read(pid: int) -> int | None:
        buffer = ctypes.create_string_buffer(_RUSAGE_BUFFER_BYTES)
        if proc_pid_rusage(pid, _RUSAGE_INFO_V0, buffer) != 0:
            return None
        field = buffer.raw[_PHYS_FOOTPRINT_OFFSET : _PHYS_FOOTPRINT_OFFSET + 8]
        return int.from_bytes(field, sys.byteorder)

    return read


def parse_vm_rss(status: str) -> int | None:
    """Bytes from the ``VmRSS`` line of /proc/<pid>/status (absent for kernel threads and zombies)."""
    match = _VM_RSS.search(status)
    return int(match.group(1)) * 1024 if match else None


def _linux_read(pid: int) -> int | None:
    try:
        return parse_vm_rss(Path(f"/proc/{pid}/status").read_text(encoding="utf-8"))
    except OSError:
        return None


def platform_reader() -> FootprintReader | None:
    """The reader for this OS, or None where no footprint source exists (the guard stays off)."""
    if sys.platform == "darwin":
        return _darwin_reader()
    if sys.platform.startswith("linux"):
        return _linux_read
    return None


def measure(
    root_pid: int,
    *,
    reader: FootprintReader | None = None,
    samples: dict[int, process_tree.ProcSample] | None = None,
    limit: int | None = None,
) -> Measurement | None:
    """Footprint of ``root_pid`` and every descendant; None when it cannot be measured.

    A process that exits between the ``ps`` snapshot and its read contributes nothing:
    the figure is a lower bound taken at one instant, which is all a ceiling check needs.
    """
    read = reader or platform_reader()
    if read is None:
        return None
    tree = process_tree.descendants(
        process_tree.snapshot() if samples is None else samples, [root_pid]
    )
    if root_pid not in tree:
        return None
    readings = {pid: read(pid) for pid in sorted(tree)}
    return Measurement(
        root_pid=root_pid,
        pids=tuple(pid for pid, size in readings.items() if size is not None),
        footprint_bytes=sum(size for size in readings.values() if size is not None),
        limit_bytes=limit_bytes() if limit is None else limit,
    )
