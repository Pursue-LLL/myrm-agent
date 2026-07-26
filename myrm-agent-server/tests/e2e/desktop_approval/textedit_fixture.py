"""TextEdit fixture helpers for desktop approval Chrome E2E (macOS only)."""

from __future__ import annotations

import asyncio
import platform
import subprocess
import time

import pytest

from tests.e2e.desktop_approval.constants import TEXTEDIT_FIXTURE_MARKER, progress


def textedit_fixture_ready() -> bool:
    if platform.system() != "Darwin":
        return False
    proc = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if not running then return false",
            "-e",
            "if (count of documents) is 0 then return false",
            "-e",
            f'return text of document 1 contains "{TEXTEDIT_FIXTURE_MARKER}"',
            "-e",
            "end tell",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _probe_textedit_ax_ready() -> tuple[bool, str]:
    """Return whether TextEdit AX snapshot currently has usable refs."""
    if platform.system() != "Darwin":
        return False, "unsupported-platform"
    from myrm_agent_harness.toolkits.computer_use.backends.macos import MacOSBackend
    from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef
    from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import (
        capture_snapshot,
    )

    backend = MacOSBackend()
    probes: tuple[tuple[str, str | None], ...] = (
        ("window_title", "TextEdit"),
        ("foreground", None),
    )
    diagnostics: list[str] = []
    for scope, window_title in probes:
        try:
            meta, refs = capture_snapshot(backend, scope, window_title)
        except Exception as exc:  # noqa: BLE001 - diagnostics for E2E recovery
            diagnostics.append(f"{scope}: {type(exc).__name__}: {exc}")
            continue
        ref_count = sum(1 for value in refs.values() if isinstance(value, ElementRef))
        if ref_count <= 0:
            diagnostics.append(
                f"{scope}: empty refs app={meta.app_name!r} window={meta.window_title!r}"
            )
            continue
        if scope == "window_title" and str(meta.app_name or "").strip() != "TextEdit":
            diagnostics.append(
                f"{scope}: unexpected app {meta.app_name!r} with refs={ref_count}"
            )
            continue
        return (
            True,
            f"{scope}: app={meta.app_name!r} window={meta.window_title!r} refs={ref_count}",
        )
    detail = "; ".join(diagnostics[:4]) if diagnostics else "no-probe-result"
    return False, detail


def prepare_textedit_fixture() -> None:
    """Open TextEdit in the background and seed scrollable fixture text without stealing focus."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["open", "-gj", "-a", "TextEdit"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if not running then launch",
            "-e",
            "if (count of documents) is 0 then make new document",
            "-e",
            'set text of document 1 to "E2E desktop control scroll target line 1" & return & "E2E desktop control scroll target line 2" & return & "E2E desktop control scroll target line 3" & return & "E2E desktop control scroll target line 4" & return & "E2E desktop control scroll target line 5"',
            "-e",
            "end tell",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def restart_textedit_fixture_process() -> None:
    """Hard-restart TextEdit when AX snapshots remain empty."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "TextEdit" to quit'],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    time.sleep(0.6)
    prepare_textedit_fixture()


def hide_textedit_fixture() -> None:
    """Keep the fixture reachable via AX without stealing user focus."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to tell process "TextEdit" to repeat with w in windows',
            "-e",
            "set miniaturized of w to true",
            "-e",
            "end repeat",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def activate_textedit_foreground() -> None:
    """Bring TextEdit to the foreground so macOS AX snapshot returns @drefs."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit" to activate',
            "-e",
            'tell application "System Events" to tell process "TextEdit" to repeat with w in windows',
            "-e",
            "set miniaturized of w to false",
            "-e",
            "end repeat",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


def activate_chrome_foreground() -> None:
    """Bring Chrome E2E browser to the foreground for CDP polling and approval UI."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def textedit_is_frontmost() -> bool:
    """True when TextEdit is the frontmost app (AX snapshot targets foreground window)."""
    if platform.system() != "Darwin":
        return False
    proc = subprocess.run(
        [
            "osascript",
            "-e",
            "tell application \"System Events\" to return name of first application process whose frontmost is true",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "TextEdit"


def preflight_textedit_foreground(
    *,
    attempts: int = 5,
    fail_hard: bool = True,
) -> bool:
    """Ensure TextEdit is un-minimized and frontmost before agent desktop tools run."""
    if platform.system() != "Darwin":
        return True
    for attempt in range(1, attempts + 1):
        activate_textedit_foreground()
        time.sleep(0.35)
        is_frontmost = textedit_is_frontmost()
        if is_frontmost:
            progress(f"textedit foreground preflight ok (attempt {attempt}/{attempts})")
            return True
        progress(
            f"textedit foreground preflight retry {attempt}/{attempts} "
            f"(frontmost={is_frontmost})"
        )
    if not fail_hard:
        return False
    pytest.fail(
        "TextEdit not frontmost after preflight — desktop_snapshot will miss @drefs "
        "and the model may fall back to desktop_vision_tool"
    )
    return False


def ensure_textedit_ax_ready(*, attempts: int = 3) -> bool:
    """Ensure TextEdit AX tree is usable, with process rebuild on failure."""
    if platform.system() != "Darwin":
        return True
    last_detail = "unknown"
    for attempt in range(1, attempts + 1):
        foreground_ok = preflight_textedit_foreground(attempts=3, fail_hard=False)
        ax_ready, detail = _probe_textedit_ax_ready()
        last_detail = detail
        if foreground_ok and ax_ready:
            progress(f"textedit AX probe ready ({detail})")
            return True
        progress(
            f"textedit AX probe not ready ({attempt}/{attempts}) "
            f"foreground_ok={foreground_ok} detail={detail}"
        )
        if attempt < attempts:
            restart_textedit_fixture_process()
            time.sleep(0.6)
    progress(f"textedit AX probe exhausted: {last_detail}")
    return False


async def ensure_textedit_fixture_ready(*, attempts: int = 5) -> None:
    if platform.system() != "Darwin":
        return
    last_detail = "unknown"
    for attempt in range(1, attempts + 1):
        await asyncio.to_thread(prepare_textedit_fixture)
        marker_ready = await asyncio.to_thread(textedit_fixture_ready)
        if marker_ready:
            ax_ready = await asyncio.to_thread(ensure_textedit_ax_ready, attempts=2)
            if ax_ready:
                progress("textedit fixture ready (foreground + AX refs for @drefs)")
                return
            last_detail = "ax-empty-after-rebuild"
        else:
            last_detail = "marker-missing"
        progress(
            f"textedit fixture not ready yet ({attempt}/{attempts}) "
            f"reason={last_detail}"
        )
        if attempt < attempts:
            await asyncio.to_thread(restart_textedit_fixture_process)
            await asyncio.sleep(0.6)
    pytest.fail(
        "TextEdit fixture not AX-ready after retries "
        f"(last_reason={last_detail}) — verify Accessibility permission and retry"
    )
