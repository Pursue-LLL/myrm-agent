"""TextEdit fixture helpers for desktop approval Chrome E2E (macOS only)."""

from __future__ import annotations

import asyncio
import platform
import subprocess

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
        timeout=20,
    )


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


async def ensure_textedit_fixture_ready(*, attempts: int = 5) -> None:
    for attempt in range(1, attempts + 1):
        await asyncio.to_thread(prepare_textedit_fixture)
        if await asyncio.to_thread(textedit_fixture_ready):
            await asyncio.to_thread(hide_textedit_fixture)
            progress("textedit fixture ready (background, minimized)")
            return
        progress(f"textedit fixture not ready yet ({attempt}/{attempts})")
        await asyncio.sleep(0.5)
    pytest.fail(
        "TextEdit fixture not ready — ensure TextEdit is installed and Accessibility is granted, then retry"
    )
