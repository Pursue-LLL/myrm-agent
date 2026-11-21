"""macOS frontmost app inspection and native API routing hints.

[INPUT]
- capture::capture_ax_snapshot (POS: AX capture whose meta describes the foreground app)
- dref.errors::AXPermissionRequiredError, AXTreeEmptyError (POS: AX error types)

[OUTPUT]
- inspect_foreground: frontmost app metadata, interactive estimate and the recommendation text for the model
- read_foreground_meta: the frontmost app's name, window title and bundle id from one osascript read (no tree, no window touched)

[POS]
Foreground probe of the macOS AX backend: a full capture when the tree is readable, a single osascript read of the
app identity when it is not (the same read is offered alone for callers that must not walk the tree), plus an
AppleScript routing hint for scriptable apps.
"""

from __future__ import annotations

import subprocess

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError, AXTreeEmptyError

from .capture import capture_ax_snapshot

_AX_FOREGROUND_META_SCRIPT = """
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set bundleId to ""
    try
        set bundleId to bundle identifier of frontApp
    end try
    set winTitle to ""
    try
        set winTitle to name of window 1 of frontApp
    end try
    return appName & "|||" & winTitle & "|||" & bundleId
end tell
"""


def read_foreground_meta() -> tuple[str, str, str]:
    """(application name, window title, bundle id) of the frontmost application from one osascript read.

    No accessibility tree is read and no window is touched, unlike ``capture_ax_snapshot``, which restores a minimized
    window. A field that cannot be read is empty; a timeout or a failed script empties all three.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", _AX_FOREGROUND_META_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return "", "", ""
    if result.returncode != 0:
        return "", "", ""
    parts = result.stdout.strip().split("|||")
    app_name = parts[0] if parts else ""
    window_title = parts[1] if len(parts) > 1 else ""
    app_id = parts[2] if len(parts) > 2 else ""
    return app_name, window_title, app_id


_SCRIPTABLE_APPS: frozenset[str] = frozenset(
    {
        "Finder",
        "Mail",
        "Safari",
        "Notes",
        "Reminders",
        "Calendar",
        "Messages",
        "Preview",
        "Music",
        "TV",
        "Podcasts",
        "Photos",
        "Keynote",
        "Pages",
        "Numbers",
        "TextEdit",
        "Terminal",
        "Script Editor",
        "System Settings",
        "System Preferences",
        "Automator",
        "Shortcuts",
        "Microsoft Excel",
        "Microsoft Word",
        "Microsoft PowerPoint",
        "Microsoft Outlook",
        "Google Chrome",
        "Slack",
        "Spotify",
        "iTerm2",
        "iTerm",
        "Adobe Photoshop",
        "Adobe Illustrator",
        "Adobe Acrobat",
        "Adobe InDesign",
        "Sketch",
        "Final Cut Pro",
        "Logic Pro",
        "GarageBand",
        "Xcode",
        "WPS Office",
        "Firefox",
        "Arc",
        "Obsidian",
        "Discord",
        "Visual Studio Code",
        "Cursor",
        "OmniGraffle",
        "DEVONthink",
        "Affinity Designer",
    }
)


_SNAPSHOT_RECOMMENDATION_BASE = (
    "Call desktop_snapshot_tool(scope='foreground') before desktop_interact_tool. "
    "To act on a background app, use desktop_snapshot_tool(scope='target', app_name='<app name>')."
)


def _native_api_hint(app_name: str) -> str:
    """Return a routing hint if the app supports AppleScript automation."""
    if app_name in _SCRIPTABLE_APPS:
        return (
            f" This app ('{app_name}') supports native AppleScript automation. "
            "For data retrieval or bulk actions, bash_code_execute_tool with osascript is faster and more reliable than GUI interaction."
        )
    return ""


def inspect_foreground() -> dict[str, str | int | bool]:
    try:
        snapshot = capture_ax_snapshot("foreground")
    except AXPermissionRequiredError:
        return {
            "app_name": "",
            "window_title": "",
            "app_id": "",
            "interactive_estimate": 0,
            "needs_permission": True,
            "recommendation": "Grant macOS Accessibility permission, then call desktop_snapshot_tool.",
        }
    except AXTreeEmptyError as exc:
        app_name, window_title, app_id = read_foreground_meta()
        base_rec = _SNAPSHOT_RECOMMENDATION_BASE
        if app_name:
            native_hint = _native_api_hint(app_name)
            return {
                "app_name": app_name,
                "window_title": window_title,
                "app_id": app_id,
                "interactive_estimate": 0,
                "needs_permission": False,
                "recommendation": f"{base_rec} AX tree had no interactive nodes ({exc}).{native_hint} Use desktop_vision_tool for canvas/custom-rendered UI.",
            }
        return {
            "app_name": "",
            "window_title": "",
            "app_id": "",
            "interactive_estimate": 0,
            "needs_permission": False,
            "recommendation": f"AX tree unavailable ({exc}). Use desktop_vision_tool fallback.",
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
