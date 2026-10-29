"""Windows process identity — executable file name for a process id.

[INPUT]
- None (ctypes kernel32 only)

[OUTPUT]
- process_name_by_pid: executable file name (``notepad.exe``) of a process id, or ``""`` when unavailable

[POS]
Process-identity primitive for Windows accessibility perception. UI Automation exposes a
window's ProcessId but has no pid-to-name lookup, so the executable name is read from Win32.
Win32 is resolved at call time, so the module imports on any platform.
"""

from __future__ import annotations

import ctypes
import functools
import ntpath
from ctypes import wintypes

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# Win32 MAX_PATH is 260 characters; 1024 also covers long-path installs without a per-call 64 KiB buffer.
_IMAGE_PATH_CHARS = 1024


@functools.cache
def _kernel32() -> ctypes.CDLL:
    """Return kernel32 with the process-query prototypes declared.

    Without prototypes ctypes truncates the 64-bit HANDLE ``OpenProcess`` returns to a 32-bit int. A private library
    instance keeps these prototypes off the process-wide ``ctypes.windll.kernel32`` other libraries share.
    """
    kernel32: ctypes.CDLL = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def process_name_by_pid(pid: int) -> str:
    """Return the executable file name of *pid* (``notepad.exe``), or ``""`` when it cannot be resolved.

    Protected and elevated processes refuse ``OpenProcess`` even with the limited-query right; they resolve to ``""``.
    """
    if pid <= 0:
        return ""
    try:
        kernel32 = _kernel32()
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(_IMAGE_PATH_CHARS)
            image_path = ctypes.create_unicode_buffer(_IMAGE_PATH_CHARS)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, image_path, ctypes.byref(size)):
                return ""
            return ntpath.basename(image_path.value)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
