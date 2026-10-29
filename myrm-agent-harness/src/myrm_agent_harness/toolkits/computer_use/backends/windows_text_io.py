"""Windows desktop text I/O — clipboard text and UI Automation window text.

[INPUT]
- types::WindowTextResult (POS: shared type definitions)

[OUTPUT]
- get_clipboard_text / set_clipboard_text: Win32 clipboard text access (CF_UNICODETEXT)
- extract_window_text: foreground window text collected through the uiautomation library

[POS]
Text bridges between the Windows desktop and the Windows backend: clipboard paste for
non-ASCII input and window text for perception. Win32 and uiautomation are resolved at
call time so the module imports on any platform.
"""

from __future__ import annotations

import ctypes
import functools
import logging
from ctypes import wintypes

from myrm_agent_harness.toolkits.computer_use.types import WindowTextResult

logger = logging.getLogger(__name__)


@functools.cache
def _win32() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    """Return ``(user32, kernel32)`` with the clipboard prototypes declared.

    ctypes reads every undeclared return value as a 32-bit int, which truncates the 64-bit pointer ``GlobalLock``
    returns and the memory handle ``GlobalAlloc`` returns. Private library instances keep these prototypes off the
    process-wide ``ctypes.windll`` objects other libraries share.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = (wintypes.UINT,)
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = (wintypes.HANDLE,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (wintypes.HANDLE,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (wintypes.HANDLE,)
    kernel32.GlobalFree.restype = wintypes.HANDLE
    return user32, kernel32


def get_clipboard_text() -> str | None:
    """Read clipboard text via Win32 API (zero-subprocess, <1ms)."""
    try:
        user32, kernel32 = _win32()

        cf_unicodetext = 13
        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(cf_unicodetext)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None


def set_clipboard_text(text: str) -> None:
    """Set clipboard text via Win32 API (zero-subprocess, <1ms)."""
    try:
        user32, kernel32 = _win32()

        cf_unicodetext = 13
        gmem_moveable = 0x0002

        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(gmem_moveable, len(encoded))
        if not h_mem:
            return
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return
        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)

        # Use foreground window as owner to ensure SetClipboardData succeeds
        hwnd = user32.GetForegroundWindow() or None
        if not user32.OpenClipboard(hwnd):
            kernel32.GlobalFree(h_mem)
            return
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(cf_unicodetext, h_mem)
        finally:
            user32.CloseClipboard()
    except Exception:
        pass


def extract_window_text() -> WindowTextResult:
    """Extract text from foreground window via uiautomation library."""
    try:
        import uiautomation as auto

        control = auto.GetForegroundControl()
        if control is None:
            return WindowTextResult(success=False)

        app_name = control.Name or ""
        window_title = app_name

        # Traverse children to extract text content (limit depth to avoid perf issues)
        text_parts: list[str] = []
        _collect_text_recursive(control, text_parts, max_depth=5, max_elements=500)

        return WindowTextResult(
            app_name=app_name,
            window_title=window_title,
            text="\n".join(text_parts),
            success=True,
        )
    except ImportError:
        logger.warning("uiautomation not installed — window_text unavailable on Windows")
        return WindowTextResult(success=False)
    except Exception as e:
        logger.warning("Windows window text extraction failed: %s", e)
        return WindowTextResult(success=False)


def _collect_text_recursive(
    control: object,
    text_parts: list[str],
    max_depth: int,
    max_elements: int,
) -> None:
    """Recursively collect text from UI Automation elements."""
    if max_depth <= 0 or len(text_parts) >= max_elements:
        return

    try:
        children = control.GetChildren()  # type: ignore[attr-defined]
        for child in children:
            if len(text_parts) >= max_elements:
                break

            control_type = getattr(child, "ControlTypeName", "")
            if control_type in ("EditControl", "TextControl", "DocumentControl"):
                try:
                    pattern = child.GetValuePattern()
                    value = pattern.Value if pattern else ""
                    if value:
                        text_parts.append(value)
                        continue
                except Exception:
                    pass
                try:
                    name = child.Name
                    if name:
                        text_parts.append(name)
                        continue
                except Exception:
                    pass

            _collect_text_recursive(child, text_parts, max_depth - 1, max_elements)
    except Exception:
        pass
