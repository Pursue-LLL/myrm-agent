"""Thread counts of one process, per platform.

[INPUT]
- libproc ``proc_pidinfo`` with flavor ``PROC_PIDTASKINFO`` (macOS)

[OUTPUT]
- ThreadCounts: threads in the process and how many of them are running right now
- ThreadReader: pid -> ThreadCounts, None when the process is gone or not readable by this user
- platform_thread_reader() -> ThreadReader | None
- thread_counts_from_taskinfo(buffer) -> ThreadCounts

[POS]
The load average counts runnable threads, not busy cores: a host can show a load of 140 with
ten cores busy when a few processes keep far more threads than cores in the running state.
Those counts tell that case apart from many single-threaded busy processes. macOS only: Linux
exposes the thread total in /proc but no cheap running count, and the recorder that uses this
needs launchd anyway.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

# `struct proc_taskinfo` (sys/proc_info.h): six u64 counters, then twelve i32 fields in the order
# policy, faults, pageins, cow_faults, messages_sent, messages_received, syscalls_mach,
# syscalls_unix, csw, threadnum, numrunning, priority.
_PROC_PIDTASKINFO: Final = 4
_TASKINFO_BYTES: Final = 6 * 8 + 12 * 4
_THREADNUM_OFFSET: Final = 6 * 8 + 9 * 4
_NUMRUNNING_OFFSET: Final = _THREADNUM_OFFSET + 4
_LIBPROC_FALLBACK: Final = "/usr/lib/libproc.dylib"


@dataclass(frozen=True, slots=True)
class ThreadCounts:
    total: int
    running: int


# One process -> its thread counts, or None when it is gone or unreadable.
ThreadReader = Callable[[int], ThreadCounts | None]


def _int32(buffer: bytes, offset: int) -> int:
    return int.from_bytes(buffer[offset : offset + 4], sys.byteorder, signed=True)


def thread_counts_from_taskinfo(buffer: bytes) -> ThreadCounts:
    """``pti_threadnum`` and ``pti_numrunning`` out of a ``proc_taskinfo`` buffer."""
    if len(buffer) < _TASKINFO_BYTES:
        raise ValueError(
            f"proc_taskinfo needs {_TASKINFO_BYTES} bytes, got {len(buffer)}"
        )
    return ThreadCounts(
        total=_int32(buffer, _THREADNUM_OFFSET),
        running=_int32(buffer, _NUMRUNNING_OFFSET),
    )


def _darwin_reader() -> ThreadReader | None:
    try:
        libproc = ctypes.CDLL(
            ctypes.util.find_library("proc") or _LIBPROC_FALLBACK, use_errno=True
        )
        proc_pidinfo = libproc.proc_pidinfo
    except (OSError, AttributeError):
        return None
    proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    proc_pidinfo.restype = ctypes.c_int

    def read(pid: int) -> ThreadCounts | None:
        buffer = ctypes.create_string_buffer(_TASKINFO_BYTES)
        written = proc_pidinfo(pid, _PROC_PIDTASKINFO, 0, buffer, _TASKINFO_BYTES)
        if written != _TASKINFO_BYTES:
            return None
        return thread_counts_from_taskinfo(buffer.raw)

    return read


def platform_thread_reader() -> ThreadReader | None:
    """The reader for this OS, or None where no thread source exists (rows omit the fields)."""
    return _darwin_reader() if sys.platform == "darwin" else None
