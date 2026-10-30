"""Linux AT-SPI snapshot with graceful fallback; the active X11 window, not AT-SPI, names the foreground app."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, replace

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError
from myrm_agent_harness.toolkits.computer_use.dref.types import (
    BBox,
    ElementRef,
    SnapshotMeta,
    SnapshotScope,
)
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

logger = logging.getLogger(__name__)

_MAX_ELEMENTS = 500

# One X11 query must not stall the safety check that depends on it.
_X11_QUERY_TIMEOUT_S = 2
_QUOTED_STRING = re.compile(r'"([^"]*)"')

_INTERACTIVE_ROLES: frozenset[str] = frozenset(
    {
        "push button",
        "check box",
        "text",
        "entry",
        "menu item",
        "radio button",
        "combo box",
        "link",
    }
)


@dataclass(frozen=True)
class LinuxAxSnapshot:
    meta: SnapshotMeta
    refs: dict[str, ElementRef]


def _try_pyatspi_snapshot(
    target_app: str | None = None,
    query: str | None = None,
    role: str | None = None,
) -> LinuxAxSnapshot | None:
    try:
        import pyatspi
    except ImportError:
        return None

    desktop = pyatspi.Registry.getDesktop(0)
    if desktop.childCount == 0:
        return None

    refs: dict[str, ElementRef] = {}
    app_name = ""
    window_title = ""
    app_id = ""
    counter = 0

    query_lower = (query or "").lower().strip()
    role_lower = (role or "").lower().strip()

    def walk(node: object) -> None:
        nonlocal counter, app_name, window_title, app_id
        if counter >= _MAX_ELEMENTS:
            return
        try:
            role_name = node.getRoleName()  # type: ignore[attr-defined]
            name = node.name or ""  # type: ignore[attr-defined]
            node.getState()  # type: ignore[attr-defined]
        except Exception:
            return

        if role_name in {"frame", "window"} and not window_title:
            window_title = name
        if role_name in {"application"} and not app_name:
            app_name = name
            if name:
                app_id = f"linux:{name.strip().lower()}"

        if role_name in _INTERACTIVE_ROLES:
            match_query = True
            if query_lower:
                match_query = query_lower in name.lower()

            match_role = True
            if role_lower:
                match_role = role_lower in role_name.lower()

            if match_query and match_role:
                try:
                    component = node.queryComponent()  # type: ignore[attr-defined]
                    extents = component.getExtents(0)
                except Exception:
                    extents = None
                if extents and extents.width > 0 and extents.height > 0:
                    ref_id = f"d{counter}"
                    refs[ref_id] = ElementRef(
                        ref_id=ref_id,
                        role=role_name,
                        name=name,
                        bbox=BBox(extents.x, extents.y, extents.width, extents.height),
                        backend_key=str(counter),
                        actions=(("click", "fill") if role_name in {"text", "entry"} else ("click",)),
                    )
                    counter += 1

        try:
            for idx in range(node.childCount):  # type: ignore[attr-defined]
                walk(node.getChildAtIndex(idx))  # type: ignore[attr-defined]
        except Exception:
            return

    target_lower = target_app.strip().lower() if target_app else ""
    for idx in range(desktop.childCount):
        child = desktop.getChildAtIndex(idx)
        if target_lower:
            try:
                child_role = child.getRoleName()
                child_name = child.name or ""
            except Exception:
                continue
            if child_role != "application" or child_name.strip().lower() != target_lower:
                continue
        walk(child)

    if not refs:
        return None

    meta = SnapshotMeta(
        ref_count=len(refs),
        app_name=app_name,
        window_title=window_title,
        scope="foreground" if not target_lower else "target",
        app_id=app_id,
        truncated=counter >= _MAX_ELEMENTS,
    )
    return LinuxAxSnapshot(meta=meta, refs=refs)


def _x11_query(argv: list[str]) -> str:
    """Stdout of one X11 helper command; empty when the tool is missing, times out or fails."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_X11_QUERY_TIMEOUT_S, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _read_foreground_meta() -> tuple[str, str]:
    """(application name, window title) of the active X11 window, read without AT-SPI.

    The application name is the window's WM_CLASS class. Either field is empty when it cannot be read.
    """
    win_id = _x11_query(["xdotool", "getactivewindow"])
    if not win_id:
        return "", ""
    title = _x11_query(["xdotool", "getwindowname", win_id])
    # xprop prints: WM_CLASS(STRING) = "instance", "Class"
    quoted = _QUOTED_STRING.findall(_x11_query(["xprop", "-id", win_id, "WM_CLASS"]))
    return (quoted[-1] if quoted else ""), title


def _with_x11_identity(snapshot: LinuxAxSnapshot) -> LinuxAxSnapshot:
    """Name the snapshot's application after the active X11 window.

    AT-SPI lists every running application, so the first one it yields is not the foreground one; the sensitive-app
    guard keys on this name. The AT-SPI name stays when X11 cannot name the active window.
    """
    wm_class, title = _read_foreground_meta()
    app_name = wm_class or title
    if not app_name:
        return snapshot
    # The title belongs to the same window as the name; the AT-SPI title may belong to another application.
    meta = replace(snapshot.meta, app_name=app_name, window_title=title, app_id=f"linux:{app_name.strip().lower()}")
    return LinuxAxSnapshot(meta=meta, refs=snapshot.refs)


def capture_ax_snapshot(
    scope: SnapshotScope,
    app_name: str | None = None,
    query: str | None = None,
    role: str | None = None,
) -> LinuxAxSnapshot:
    if scope == "target":
        if not app_name:
            raise AXTreeEmptyError("target scope requires app_name")
        snapshot = _try_pyatspi_snapshot(target_app=app_name, query=query, role=role)
        if snapshot is None:
            raise AXTreeEmptyError(f"target window not found for app '{app_name}'")
        return snapshot

    pyatspi_snapshot = _try_pyatspi_snapshot(query=query, role=role)
    if pyatspi_snapshot is not None:
        return _with_x11_identity(pyatspi_snapshot)

    if shutil.which("xdotool") is None:
        raise AXTreeEmptyError("pyatspi unavailable and xdotool missing")

    try:
        proc = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise AXTreeEmptyError("Linux AX snapshot failed") from exc

    title = proc.stdout.strip() if proc.returncode == 0 else ""
    if not title:
        raise AXTreeEmptyError("no active window title")

    raise AXTreeEmptyError("AT-SPI tree unavailable in this environment. Install pyatspi or use desktop_vision_tool.")


def invoke_ax_element(
    backend_key: str,
    action: str,
    text: str = "",
    app_name: str | None = None,
) -> ActionResult:
    """Invoke an AT-SPI element by flat-index (mirrors Windows UIA pattern)."""
    try:
        index = int(backend_key)
    except (ValueError, TypeError):
        return ActionResult(success=False, error=f"Invalid backend_key: {backend_key}")
    if index < 0 or index >= _MAX_ELEMENTS:
        return ActionResult(success=False, error=f"Index {index} out of range [0, {_MAX_ELEMENTS})")

    try:
        import pyatspi
    except ImportError:
        return ActionResult(
            success=False,
            error="pyatspi not available; use desktop_vision_tool fallback",
        )

    desktop = pyatspi.Registry.getDesktop(0)
    if desktop.childCount == 0:
        return ActionResult(success=False, error="AT-SPI desktop has no applications")

    interactive: list[object] = []

    def _collect(node: object) -> None:
        if len(interactive) > index:
            return
        try:
            role_name = node.getRoleName()  # type: ignore[attr-defined]
            node.getState()  # type: ignore[attr-defined]
        except Exception:
            return
        if role_name in _INTERACTIVE_ROLES:
            try:
                component = node.queryComponent()  # type: ignore[attr-defined]
                extents = component.getExtents(0)
            except Exception:
                extents = None
            if extents and extents.width > 0 and extents.height > 0:
                interactive.append(node)
        try:
            for i in range(node.childCount):  # type: ignore[attr-defined]
                _collect(node.getChildAtIndex(i))  # type: ignore[attr-defined]
        except Exception:
            return

    target_lower = app_name.strip().lower() if app_name else ""
    for i in range(desktop.childCount):
        node = desktop.getChildAtIndex(i)
        if target_lower:
            try:
                node_role = node.getRoleName()
                node_name = node.name or ""
            except Exception:
                continue
            if node_role != "application" or node_name.strip().lower() != target_lower:
                continue
        _collect(node)

    if index >= len(interactive):
        return ActionResult(success=False, error=f"Stale element index {index}")

    target = interactive[index]
    normalized = action.lower()
    try:
        if normalized in {"fill", "type", "set_value"}:
            try:
                editable = target.queryEditableText()  # type: ignore[attr-defined]
                editable.setTextContents(text)
            except Exception:
                # Typing is the backend's job (stdin/clipboard, UTF-8 locale, cancellable); failing here hands the
                # element to the caller's coordinate fallback, which clicks it and types through the backend.
                return ActionResult(success=False, error="element exposes no editable text interface")
        elif normalized in {
            "click",
            "press",
            "hover",
            "focus",
            "dblclick",
            "double_click",
            "toggle",
            "expand",
            "collapse",
            "invoke",
            "check",
            "uncheck",
        }:
            try:
                action_if = target.queryAction()  # type: ignore[attr-defined]
                if action_if.getNActions() > 0:
                    action_if.doAction(0)
                else:
                    target.queryComponent().grabFocus()  # type: ignore[attr-defined]
            except Exception:
                target.queryComponent().grabFocus()  # type: ignore[attr-defined]
        else:
            return ActionResult(success=False, error=f"Unsupported action: {action}")
    except Exception as exc:
        return ActionResult(success=False, error=str(exc))
    return ActionResult(success=True, output=f"AT-SPI {normalized} succeeded")


_DBUS_AUTOMATABLE_APPS: frozenset[str] = frozenset(
    {
        "nautilus",
        "Files",
        "Thunderbird",
        "LibreOffice",
        "gedit",
        "GNOME Terminal",
        "Rhythmbox",
        "Totem",
        "Evince",
        "Eye of GNOME",
        "Firefox",
        "GIMP",
        "Inkscape",
        "VLC",
        "Kate",
        "Konsole",
        "WPS Office",
        "Okular",
        "Dolphin",
        "KCalc",
    }
)

_SNAPSHOT_RECOMMENDATION_BASE = (
    "Call desktop_snapshot_tool(scope='foreground') before desktop_interact_tool. "
    "To act on a background app, use desktop_snapshot_tool(scope='target', app_name='<app name>')."
)


def _native_api_hint(app_name: str) -> str:
    """Return a routing hint if the app supports D-Bus/CLI automation."""
    for known in _DBUS_AUTOMATABLE_APPS:
        if known.lower() in app_name.lower():
            return (
                f" This app ('{app_name}') supports D-Bus or CLI automation. "
                "For data retrieval or bulk actions, bash_code_execute_tool with dbus-send/gdbus or CLI flags is faster than GUI interaction."
            )
    return ""


def inspect_foreground() -> dict[str, str | int | bool]:
    try:
        snapshot = capture_ax_snapshot("foreground")
    except AXTreeEmptyError as exc:
        # The sensitive-app guard keys on this name, so an unreadable AT-SPI tree must not erase the app identity.
        wm_class, title = _read_foreground_meta()
        return {
            "app_name": wm_class or title,
            "window_title": title,
            "interactive_estimate": 0,
            "needs_permission": False,
            "recommendation": str(exc),
        }

    base_rec = _SNAPSHOT_RECOMMENDATION_BASE
    native_hint = _native_api_hint(snapshot.meta.app_name)
    return {
        "app_name": snapshot.meta.app_name,
        "window_title": snapshot.meta.window_title,
        "app_id": snapshot.meta.app_id,
        "interactive_estimate": snapshot.meta.ref_count,
        "needs_permission": False,
        "recommendation": base_rec + native_hint,
    }
