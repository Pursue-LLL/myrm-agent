"""Platform dispatch for desktop AX snapshot capture.

[INPUT]
- backends.protocols::ComputerBackend (POS: platform I/O protocol)
- perception.{macos_ax,windows_ax,linux_ax} (POS: platform AX capture/invoke)
- dref.types::ElementRef, SnapshotMeta, SnapshotScope (POS: @dref types)
- ax_result::{AxFailure, AxInvokeResult} (POS: typed outcome of a native action)

[OUTPUT]
- capture_snapshot: platform-routed AX snapshot capture
- inspect_backend: frontmost app metadata inspection
- invoke_element: platform-routed AX element invocation; a failure carries what it proves about delivery
- run_ax_call: awaits a blocking AX or osascript call without stalling the event loop where that is verified safe

[POS]
Platform routing dispatch for AX snapshot/invoke. Routes to macOS/Windows/Linux backend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from myrm_agent_harness.toolkits.computer_use.backends.protocols import ComputerBackend
from myrm_agent_harness.toolkits.computer_use.dref.types import (
    ElementRef,
    SnapshotMeta,
    SnapshotScope,
)
from myrm_agent_harness.toolkits.computer_use.perception import (
    linux_ax,
    macos_ax,
    windows_ax,
)
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult

logger = logging.getLogger(__name__)


def capture_snapshot(
    backend: ComputerBackend,
    scope: SnapshotScope,
    app_name: str | None = None,
    query: str | None = None,
    role: str | None = None,
) -> tuple[SnapshotMeta, dict[str, ElementRef]]:
    platform = type(backend).__name__
    if platform == "MacOSBackend":
        macos_snapshot = macos_ax.capture_ax_snapshot(scope, app_name=app_name, query=query, role=role)
        return macos_snapshot.meta, macos_snapshot.refs
    if platform == "WindowsBackend":
        windows_snapshot = windows_ax.capture_ax_snapshot(scope, app_name=app_name, query=query, role=role)
        return windows_snapshot.meta, windows_snapshot.refs
    if platform == "LinuxBackend":
        linux_snapshot = linux_ax.capture_ax_snapshot(scope, app_name=app_name, query=query, role=role)
        return linux_snapshot.meta, linux_snapshot.refs
    raise RuntimeError(f"Unsupported backend for AX snapshot: {platform}")


def inspect_backend(backend: ComputerBackend) -> dict[str, str | int | bool]:
    platform = type(backend).__name__
    if platform == "MacOSBackend":
        return macos_ax.inspect_foreground()
    if platform == "WindowsBackend":
        return windows_ax.inspect_foreground()
    if platform == "LinuxBackend":
        return linux_ax.inspect_foreground()
    return {
        "app_name": "",
        "window_title": "",
        "interactive_estimate": 0,
        "needs_permission": False,
        "recommendation": "Use desktop_snapshot_tool, then desktop_vision_tool fallback if needed.",
    }


def invoke_element(
    backend: ComputerBackend,
    element: ElementRef,
    action: str,
    text: str = "",
    app_name: str | None = None,
) -> AxInvokeResult:
    platform = type(backend).__name__
    if platform == "MacOSBackend":
        return macos_ax.invoke_ax_element(element.backend_key, action, text, app_name=app_name)
    if platform == "WindowsBackend":
        return windows_ax.invoke_ax_element(element.backend_key, action, text, app_name=app_name)
    if platform == "LinuxBackend":
        return linux_ax.invoke_ax_element(element.backend_key, action, text, role=element.role, name=element.name)
    return AxInvokeResult.failed(AxFailure.UNSUPPORTED, f"Unsupported backend for AX invoke: {platform}")


async def run_ax_call[**P, R](
    backend: ComputerBackend, call: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Await a blocking AX or osascript call without freezing the event loop on macOS.

    The macOS capture, invoke and foreground reads wait on an osascript child for up to 15 s; on the loop thread that
    stops every other chat in the process, so a worker thread runs them (they touch no in-process AppKit state). The
    other platforms run inline: the thread rules of their UIA (COM) and AT-SPI bindings are not checked here.
    Callers keep every registry write on the loop thread by awaiting this for the read only.
    """
    if type(backend).__name__ == "MacOSBackend":
        return await asyncio.to_thread(call, *args, **kwargs)
    return call(*args, **kwargs)
