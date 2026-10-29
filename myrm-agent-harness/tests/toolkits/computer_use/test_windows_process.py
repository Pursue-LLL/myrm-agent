"""Tests for windows_process.process_name_by_pid.

Covers:
- executable file name extracted from the full image path
- OpenProcess / QueryFullProcessImageNameW failures resolve to an empty name and never leak the handle
- non-positive pids never reach Win32
- ctypes prototypes are declared so the 64-bit process HANDLE is not truncated
- the prototypes live on a private kernel32 instance, not the shared ctypes.windll
- platforms without ctypes.WinDLL resolve to an empty name
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.perception import windows_process
from myrm_agent_harness.toolkits.computer_use.perception.windows_process import process_name_by_pid

_PROCESS_HANDLE = 0x1234


def _kernel32(image_path: str | None = "C:\\Windows\\System32\\notepad.exe", *, handle: int | None = _PROCESS_HANDLE):
    """A kernel32 double: OpenProcess yields *handle*; the image query fills the buffer, or fails when *image_path* is None."""
    kernel32 = MagicMock()
    kernel32.OpenProcess.return_value = handle

    def _query(_handle, _flags, buffer, _size) -> int:
        if image_path is None:
            return 0
        buffer.value = image_path
        return 1

    kernel32.QueryFullProcessImageNameW.side_effect = _query
    return kernel32


@pytest.fixture(autouse=True)
def _fresh_kernel32_cache():
    """The loader is cached; keep one test's double from leaking into the next."""
    windows_process._kernel32.cache_clear()
    yield
    windows_process._kernel32.cache_clear()


def _call(kernel32: MagicMock, pid: int = 4242) -> str:
    with patch.object(ctypes, "WinDLL", return_value=kernel32, create=True):
        return process_name_by_pid(pid)


class TestProcessNameByPid:
    def test_returns_executable_file_name(self) -> None:
        kernel32 = _kernel32()
        assert _call(kernel32) == "notepad.exe"
        kernel32.OpenProcess.assert_called_once_with(0x1000, False, 4242)
        kernel32.CloseHandle.assert_called_once_with(_PROCESS_HANDLE)

    def test_open_process_failure_returns_empty_without_querying(self) -> None:
        kernel32 = _kernel32(handle=None)
        assert _call(kernel32) == ""
        kernel32.QueryFullProcessImageNameW.assert_not_called()
        kernel32.CloseHandle.assert_not_called()

    def test_query_failure_returns_empty_and_closes_handle(self) -> None:
        kernel32 = _kernel32(image_path=None)
        assert _call(kernel32) == ""
        kernel32.CloseHandle.assert_called_once_with(_PROCESS_HANDLE)

    def test_win32_exception_returns_empty(self) -> None:
        kernel32 = _kernel32()
        kernel32.OpenProcess.side_effect = OSError("access denied")
        assert _call(kernel32) == ""

    @pytest.mark.parametrize("pid", [0, -1])
    def test_non_positive_pid_never_reaches_win32(self, pid: int) -> None:
        kernel32 = _kernel32()
        assert _call(kernel32, pid) == ""
        kernel32.OpenProcess.assert_not_called()

    def test_prototypes_keep_the_handle_pointer_sized(self) -> None:
        kernel32 = _kernel32()
        _call(kernel32)
        assert kernel32.OpenProcess.restype is wintypes.HANDLE
        assert kernel32.QueryFullProcessImageNameW.argtypes[0] is wintypes.HANDLE
        assert kernel32.CloseHandle.argtypes == (wintypes.HANDLE,)

    def test_prototypes_live_on_a_private_library_instance(self) -> None:
        kernel32 = _kernel32()
        windll = MagicMock()
        with (
            patch.object(ctypes, "windll", windll, create=True),
            patch.object(ctypes, "WinDLL", return_value=kernel32, create=True) as win_dll,
        ):
            process_name_by_pid(4242)
        win_dll.assert_called_once_with("kernel32", use_last_error=True)
        windll.kernel32.OpenProcess.assert_not_called()

    def test_platform_without_win_dll_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(ctypes, "WinDLL", raising=False)
        assert process_name_by_pid(4242) == ""
