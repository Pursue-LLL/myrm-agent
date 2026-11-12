"""Physical-memory footprint of one process, per platform.

[INPUT]
- libproc ``proc_pid_rusage`` (macOS) and /proc/<pid>/status (Linux)

[OUTPUT]
- FootprintReader: pid -> footprint bytes, None when the process is gone or unreadable
- platform_reader() -> FootprintReader | None
- phys_footprint_from_rusage(buffer) -> int
- parse_vm_rss(status) -> int | None

[POS]
macOS ``ri_phys_footprint`` is the figure Activity Monitor and footprint(1) show: resident
plus compressed plus swapped pages. RSS leaves compressed and swapped pages out, so under
memory pressure it understates what a process weighs on the machine (one Next dev server
read 107 MB RSS against 6971 MB footprint). Linux has no such counter without root, so it
reads VmRSS. Shared by the Next dev supervisor's memory guard and the host load recorder.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

# `struct rusage_info_v0` (sys/resource.h): uuid[16], then ri_user_time, ri_system_time,
# ri_pkg_idle_wkups, ri_interrupt_wkups, ri_pageins, ri_wired_size, ri_resident_size, and
# ri_phys_footprint as the eighth u64 field.
_RUSAGE_INFO_V0: Final = 0
_PHYS_FOOTPRINT_OFFSET: Final = 16 + 7 * 8
_RUSAGE_BUFFER_BYTES: Final = 512
_LIBPROC_FALLBACK: Final = "/usr/lib/libproc.dylib"
_VM_RSS: Final = re.compile(r"^VmRSS:\s+(\d+) kB$", re.MULTILINE)

# One process -> its footprint in bytes, or None when it is gone or unreadable.
FootprintReader = Callable[[int], int | None]


def phys_footprint_from_rusage(buffer: bytes) -> int:
    """``ri_phys_footprint`` out of a ``rusage_info_v0`` buffer."""
    field = buffer[_PHYS_FOOTPRINT_OFFSET : _PHYS_FOOTPRINT_OFFSET + 8]
    return int.from_bytes(field, sys.byteorder)


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
        return phys_footprint_from_rusage(buffer.raw)

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
