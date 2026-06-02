"""System sleep inhibitor for long-running agent tasks.

Prevents the host machine from entering idle sleep while agent tasks
are actively running. Only activates in local deployment mode (Tauri
desktop / local WebUI); sandbox and SaaS modes are always no-op.

Platform support:
  - macOS:   IOKit native API (IOPMAssertionCreateWithName)
  - Linux:   systemd-inhibit --what=idle sleep infinity
  - Windows: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
  - Other:   graceful no-op

Uses reference counting so concurrent tasks share a single inhibitor
process; the inhibitor is released only when all tasks finish.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import platform
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class SleepInhibitor:
    """Reference-counted system sleep inhibitor.

    Usage::

        async with SleepInhibitor.hold():
            # system will not idle-sleep while inside this block
            ...
    """

    _lock: asyncio.Lock | None = None
    _ref_count: int = 0
    _process: subprocess.Popen[bytes] | None = None
    _prev_exec_state: int | None = None

    _mac_assertions: list[int] = []

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    @asynccontextmanager
    async def hold(cls, prevent_display_sleep: bool = False) -> AsyncIterator[None]:
        """Acquire the sleep inhibitor for the duration of the block.

        Args:
            prevent_display_sleep: Also keep the display awake (required for CU
                sessions that need to capture actual screen content).
        """
        from app.config.deploy_mode import is_local_mode

        if not is_local_mode():
            yield
            return

        cls._ref_count += 1
        if cls._ref_count == 1:
            cls._activate(prevent_display_sleep=prevent_display_sleep)

        try:
            yield
        finally:
            cls._ref_count -= 1
            if cls._ref_count <= 0:
                cls._ref_count = 0
                cls._deactivate()

    @classmethod
    def _activate(cls, *, prevent_display_sleep: bool = False) -> None:
        system = platform.system()
        try:
            if system == "Darwin":
                import ctypes
                import ctypes.util

                core_foundation_path = ctypes.util.find_library("CoreFoundation")
                iokit_path = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
                if not core_foundation_path or not iokit_path:
                    raise FileNotFoundError("CoreFoundation or IOKit not found")
                
                core_foundation = ctypes.cdll.LoadLibrary(core_foundation_path)
                
                # CFStringCreateWithCString
                core_foundation.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
                core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
                
                # CFRelease
                core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
                core_foundation.CFRelease.restype = None
                
                # IOPMAssertionCreateWithName
                iokit_path.IOPMAssertionCreateWithName.argtypes = [
                    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
                ]
                iokit_path.IOPMAssertionCreateWithName.restype = ctypes.c_int32
                
                # IOPMAssertionRelease
                iokit_path.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
                iokit_path.IOPMAssertionRelease.restype = ctypes.c_int32

                def create_cfstring(s: str) -> int:
                    return core_foundation.CFStringCreateWithCString(None, s.encode("utf-8"), 0x08000100)

                assertion_types = [
                    "PreventUserIdleSystemSleep",
                    "PreventSystemSleep",
                ]
                if prevent_display_sleep:
                    assertion_types.append("PreventUserIdleDisplaySleep")

                reason_cf = create_cfstring("Agent task running")
                cls._mac_assertions = []
                
                try:
                    for atype in assertion_types:
                        type_cf = create_cfstring(atype)
                        assertion_id = ctypes.c_uint32(0)
                        result = iokit_path.IOPMAssertionCreateWithName(
                            type_cf,
                            255, # kIOPMAssertionLevelOn
                            reason_cf,
                            ctypes.byref(assertion_id)
                        )
                        core_foundation.CFRelease(type_cf)
                        
                        if result == 0:
                            cls._mac_assertions.append(assertion_id.value)
                        else:
                            logger.warning(f"Failed to create IOKit assertion {atype}: {result}")
                finally:
                    core_foundation.CFRelease(reason_cf)

                atexit.register(cls._cleanup_atexit)
                logger.debug("Sleep inhibitor activated (IOKit assertions: %s)", cls._mac_assertions)

            elif system == "Linux":
                cls._process = subprocess.Popen(
                    [
                        "systemd-inhibit",
                        "--what=idle",
                        "--who=myrm-agent",
                        "--why=Agent task running",
                        "sleep",
                        "infinity",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                atexit.register(cls._cleanup_atexit)
                logger.debug("Sleep inhibitor activated (systemd-inhibit pid=%d)", cls._process.pid)

            elif system == "Windows":
                import ctypes

                ES_CONTINUOUS = 0x80000000
                ES_SYSTEM_REQUIRED = 0x00000001
                ES_DISPLAY_REQUIRED = 0x00000002
                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                if prevent_display_sleep:
                    flags |= ES_DISPLAY_REQUIRED
                cls._prev_exec_state = ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
                logger.debug("Sleep inhibitor activated (SetThreadExecutionState)")

            else:
                logger.debug("Sleep inhibitor not supported on %s (no-op)", system)

        except FileNotFoundError:
            logger.debug("Sleep inhibitor tool not found on %s (no-op)", system)
        except Exception:
            logger.debug("Sleep inhibitor activation failed (non-fatal)", exc_info=True)

    @classmethod
    def _deactivate(cls) -> None:
        system = platform.system()
        try:
            if system == "Darwin" and hasattr(cls, "_mac_assertions") and cls._mac_assertions:
                try:
                    import ctypes
                    import ctypes.util
                    iokit_path_str = ctypes.util.find_library("IOKit")
                    if iokit_path_str:
                        iokit_path = ctypes.cdll.LoadLibrary(iokit_path_str)
                        iokit_path.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
                        iokit_path.IOPMAssertionRelease.restype = ctypes.c_int32
                        
                        for assertion_id in cls._mac_assertions:
                            iokit_path.IOPMAssertionRelease(assertion_id)
                finally:
                    cls._mac_assertions.clear()
                    logger.debug("Sleep inhibitor released (IOKit)")

            elif cls._process is not None:
                cls._process.terminate()
                try:
                    cls._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls._process.kill()
                    cls._process.wait(timeout=2)
                logger.debug("Sleep inhibitor released (pid=%d)", cls._process.pid)
                cls._process = None

            elif system == "Windows" and cls._prev_exec_state is not None:
                import ctypes

                ES_CONTINUOUS = 0x80000000
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # type: ignore[attr-defined]
                cls._prev_exec_state = None
                logger.debug("Sleep inhibitor released (SetThreadExecutionState)")

        except Exception:
            logger.debug("Sleep inhibitor deactivation failed (non-fatal)", exc_info=True)
            cls._process = None
            cls._prev_exec_state = None

    @classmethod
    def _cleanup_atexit(cls) -> None:
        """Safety net: kill inhibitor process on interpreter exit."""
        if hasattr(cls, "_mac_assertions") and cls._mac_assertions:
            try:
                import ctypes
                import ctypes.util
                iokit_path = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
                iokit_path.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
                iokit_path.IOPMAssertionRelease.restype = ctypes.c_int32
                for assertion_id in cls._mac_assertions:
                    iokit_path.IOPMAssertionRelease(assertion_id)
                cls._mac_assertions.clear()
            except Exception:
                pass

        if cls._process is not None:
            try:
                cls._process.terminate()
            except Exception:
                pass
            cls._process = None
