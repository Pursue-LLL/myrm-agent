"""Windows-only smoke tests against the real Win32 APIs.

The other Windows suites run on every platform against ctypes doubles, which cannot tell a wrong
prototype, a misspelled function or a wrongly sized structure from a correct one. These tests load
the real libraries and only run on a Windows host.
"""

from __future__ import annotations

import ctypes
import os
import sys

import pytest

from myrm_agent_harness.toolkits.computer_use.backends import windows_text_io
from myrm_agent_harness.toolkits.computer_use.perception import windows_process

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="exercises the real Win32 APIs")

_ERROR_INVALID_PARAMETER = 87


@pytest.fixture(autouse=True)
def _fresh_loader_caches():
    """The loaders are cached; make sure no test double from another suite is reused."""
    windows_text_io._user32.cache_clear()
    windows_process._kernel32.cache_clear()
    yield
    windows_text_io._user32.cache_clear()
    windows_process._kernel32.cache_clear()


def test_process_name_of_the_running_interpreter_is_resolved() -> None:
    name = windows_process.process_name_by_pid(os.getpid()).lower()
    assert name.startswith("python")
    assert name.endswith(".exe")


def test_process_prototypes_resolve_on_the_real_kernel32() -> None:
    assert windows_process._kernel32().OpenProcess is not None


def test_input_structure_has_the_size_of_the_running_architecture() -> None:
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(windows_text_io._Input) == expected


@pytest.mark.skipif(not os.environ.get("CI"), reason="injects a real keystroke into the focused window")
def test_send_input_accepts_the_structure_size() -> None:
    """Windows rejects a wrong cbSize with ERROR_INVALID_PARAMETER; any other outcome means the size was accepted."""
    try:
        windows_text_io.type_unicode_text("\u200b", 0, 50)
    except OSError as error:
        assert f"last error {_ERROR_INVALID_PARAMETER}" not in str(error)
