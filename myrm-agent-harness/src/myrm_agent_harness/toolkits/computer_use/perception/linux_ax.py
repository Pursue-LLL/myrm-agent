"""Linux AT-SPI snapshot with graceful fallback; the active X11 window, not AT-SPI, names the foreground app."""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError
from myrm_agent_harness.toolkits.computer_use.dref.types import (
    BBox,
    ElementRef,
    SnapshotMeta,
    SnapshotScope,
)
from myrm_agent_harness.toolkits.computer_use.perception.linux_x11 import foreground_pid, read_foreground_meta
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

logger = logging.getLogger(__name__)

_MAX_ELEMENTS = 500  # refs one snapshot returns
_MAX_ORDINAL = 5000  # interactive elements scanned per application; bounds the ordinal in a backend_key
_KEY_SEPARATOR = ":"  # between an application instance and an element's ordinal
_PID_SEPARATOR = "@"  # between an application's name and its process id

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


@dataclass(frozen=True)
class _Interactive:
    """One interactive element in AT-SPI traversal order."""

    node: object
    app_name: str
    window_title: str
    role: str
    name: str
    bbox: BBox
    # The application instance (name and process) the element belongs to.
    instance: str
    # Position among the instance's interactive elements, assigned before any query/role filter so that a
    # snapshot and a later invoke count the same elements.
    ordinal: int

    @property
    def backend_key(self) -> str:
        return f"{self.instance}{_KEY_SEPARATOR}{self.ordinal}"


def _app_key(app_name: str) -> str:
    return app_name.strip().lower()


def _node_name(node: object) -> str:
    try:
        name = node.name  # type: ignore[attr-defined]
    except Exception:
        return ""
    return name if isinstance(name, str) else ""


def _app_pid(app: object) -> int | None:
    try:
        pid = app.get_process_id()  # type: ignore[attr-defined]
    except Exception:
        return None
    return pid if isinstance(pid, int) else None


def _instance_key(app_key: str, pid: int | None) -> str:
    """Names one running application: two windows of the same program are two instances when their processes differ."""
    return f"{app_key}{_PID_SEPARATOR}{pid or ''}"


def _select_apps(desktop: object, keep: Callable[[object], bool]) -> list[object]:
    apps: list[object] = []
    for idx in range(desktop.childCount):  # type: ignore[attr-defined]
        try:
            child = desktop.getChildAtIndex(idx)  # type: ignore[attr-defined]
            if keep(child):
                apps.append(child)
        except Exception:
            continue
    return apps


def _walk(
    node: object,
    app_name: str,
    instance: str,
    window_title: str,
    ordinals: dict[str, int],
) -> Iterator[_Interactive]:
    if ordinals.get(instance, 0) >= _MAX_ORDINAL:
        return
    try:
        role_name = node.getRoleName()  # type: ignore[attr-defined]
        node.getState()  # type: ignore[attr-defined]
    except Exception:
        return
    name = _node_name(node)

    if role_name in {"frame", "window"} and not window_title:
        window_title = name

    if role_name in _INTERACTIVE_ROLES:
        try:
            extents = node.queryComponent().getExtents(0)  # type: ignore[attr-defined]
        except Exception:
            extents = None
        if extents and extents.width > 0 and extents.height > 0:
            ordinal = ordinals.get(instance, 0)
            ordinals[instance] = ordinal + 1
            yield _Interactive(
                node=node,
                app_name=app_name,
                window_title=window_title,
                role=role_name,
                name=name,
                bbox=BBox(extents.x, extents.y, extents.width, extents.height),
                instance=instance,
                ordinal=ordinal,
            )

    try:
        for idx in range(node.childCount):  # type: ignore[attr-defined]
            yield from _walk(node.getChildAtIndex(idx), app_name, instance, window_title, ordinals)  # type: ignore[attr-defined]
    except Exception:
        return


def _iter_interactive(apps: list[object]) -> Iterator[_Interactive]:
    """Interactive elements of *apps* in document order; the single source of element order for snapshot and invoke."""
    ordinals: dict[str, int] = {}
    for app in apps:
        app_name = _node_name(app)
        instance = _instance_key(_app_key(app_name), _app_pid(app))
        yield from _walk(app, app_name, instance, "", ordinals)


def _apps_of_pid(desktop: object, pid: int) -> list[object]:
    return _select_apps(desktop, lambda app: _app_pid(app) == pid)


def _foreground_apps(desktop: object) -> list[object]:
    """Applications of the active window; every application when its process cannot be matched."""
    everyone = _select_apps(desktop, lambda _app: True)
    pid = foreground_pid()
    if pid is None:
        logger.debug("Active window's process is unknown; the snapshot lists every application")
        return everyone
    scoped = _apps_of_pid(desktop, pid)
    if not scoped:
        logger.debug("No AT-SPI application runs as process %d; the snapshot lists every application", pid)
    return scoped or everyone


def _target_apps(desktop: object, target_lower: str) -> list[object]:
    """Applications named *target_lower*; the name X11 gives the active window also reaches that window's application."""
    named = _select_apps(
        desktop,
        lambda app: app.getRoleName() == "application" and _app_key(_node_name(app)) == target_lower,  # type: ignore[attr-defined]
    )
    if named:
        return named
    wm_class, title = read_foreground_meta()
    pid = foreground_pid() if _app_key(wm_class or title) == target_lower else None
    apps = _apps_of_pid(desktop, pid) if pid is not None else []
    if not apps:
        logger.debug("No AT-SPI application matches the target %r", target_lower)
    return apps


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

    target_lower = _app_key(target_app) if target_app else ""
    apps = _target_apps(desktop, target_lower) if target_lower else _foreground_apps(desktop)

    query_lower = (query or "").lower().strip()
    role_lower = (role or "").lower().strip()

    refs: dict[str, ElementRef] = {}
    first: _Interactive | None = None
    for item in _iter_interactive(apps):
        if query_lower and query_lower not in item.name.lower():
            continue
        if role_lower and role_lower not in item.role.lower():
            continue
        first = first or item
        ref_id = f"d{len(refs)}"
        refs[ref_id] = ElementRef(
            ref_id=ref_id,
            role=item.role,
            name=item.name,
            bbox=item.bbox,
            backend_key=item.backend_key,
            actions=(("click", "fill") if item.role in {"text", "entry"} else ("click",)),
        )
        if len(refs) >= _MAX_ELEMENTS:
            break

    if first is None:
        return None

    meta = SnapshotMeta(
        ref_count=len(refs),
        app_name=first.app_name,
        window_title=first.window_title,
        scope="target" if target_lower else "foreground",
        app_id=f"linux:{_app_key(first.app_name)}" if first.app_name else "",
        truncated=len(refs) >= _MAX_ELEMENTS,
    )
    return LinuxAxSnapshot(meta=meta, refs=refs)


def _with_x11_identity(snapshot: LinuxAxSnapshot) -> LinuxAxSnapshot:
    """Name the snapshot's application after the active X11 window.

    AT-SPI lists every running application, so the first one it yields is not the foreground one; the sensitive-app
    guard keys on this name. The AT-SPI name stays when X11 cannot name the active window.
    """
    wm_class, title = read_foreground_meta()
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


def _parse_backend_key(backend_key: str) -> tuple[str, int | None, int] | None:
    """Split ``<application>@<pid>:<ordinal>``; the application name may itself contain either separator.

    The pid is empty, and None here, when the application's process could not be read.
    """
    instance, key_separator, ordinal_text = backend_key.rpartition(_KEY_SEPARATOR)
    app_key, pid_separator, pid_text = instance.rpartition(_PID_SEPARATOR)
    if not key_separator or not pid_separator:
        return None
    try:
        return app_key, (int(pid_text) if pid_text else None), int(ordinal_text)
    except ValueError:
        return None


def invoke_ax_element(
    backend_key: str,
    action: str,
    text: str = "",
    *,
    role: str,
    name: str,
) -> ActionResult:
    """Invoke the AT-SPI element a snapshot named ``<application>@<pid>:<ordinal>``.

    The key carries its application instance, so the call needs neither the snapshot's app name (the foreground
    snapshot reports X11's name for the window, not AT-SPI's) nor the focus to be where it was. The interface may
    have changed since the snapshot, so the element found at that position must still have the snapshot's role and
    name; otherwise the call fails and the caller falls back to the element's coordinates.
    """
    parsed = _parse_backend_key(backend_key)
    if parsed is None:
        return ActionResult(success=False, error=f"Invalid backend_key: {backend_key}")
    app_key, pid, index = parsed
    if index < 0 or index >= _MAX_ORDINAL:
        return ActionResult(success=False, error=f"Index {index} out of range [0, {_MAX_ORDINAL})")

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

    apps = _select_apps(desktop, lambda app: _app_key(_node_name(app)) == app_key and _app_pid(app) == pid)
    found = next((item for item in _iter_interactive(apps) if item.ordinal == index), None)
    if found is None:
        return ActionResult(success=False, error=f"Stale element index {index}")
    if (found.role, found.name) != (role, name):
        # Element names are user content (subjects, titles), so the log carries only the key.
        logger.debug("AT-SPI element %s no longer matches its snapshot", backend_key)
        return ActionResult(success=False, error=f"Stale element index {index}")
    target = found.node

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
        wm_class, title = read_foreground_meta()
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
