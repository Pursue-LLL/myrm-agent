"""LinuxBackend against a real X server with the real xdotool.

The fake-tool suites cannot show what the genuine binary does (exit codes, whether non-ASCII text
arrives as key events), so CI runs this file under `xvfb-run`. It moves the pointer and types into an
xev window, so it only runs when MYRM_REAL_X11_TESTS=1 is set: never on a developer's own desktop session.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend

pytestmark = pytest.mark.skipif(
    not (
        sys.platform.startswith("linux")
        and os.environ.get("MYRM_REAL_X11_TESTS") == "1"
        and os.environ.get("DISPLAY")
        and shutil.which("xdotool")
        and shutil.which("xev")
    ),
    reason="needs MYRM_REAL_X11_TESTS=1, a DISPLAY (xvfb-run) and xdotool + xev",
)

_UNREACHABLE_DISPLAY = 987
_XEV_WINDOW_NAME = "Event Tester"


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend()


@pytest.fixture
def xev_window(tmp_path: Path) -> Iterator[Path]:
    """A focused xev window (a bare Xvfb root does not keep a warped pointer); yields the file xev logs its events to."""
    log = tmp_path / "xev.log"
    with log.open("w") as sink:
        xev = subprocess.Popen(["xev"], stdout=sink, stderr=subprocess.STDOUT)
        try:
            window = ""
            for _ in range(100):
                found = subprocess.run(
                    ["xdotool", "search", "--name", _XEV_WINDOW_NAME], capture_output=True, text=True, timeout=5
                )
                window = found.stdout.split()[0] if found.stdout.split() else ""
                if window:
                    break
                time.sleep(0.1)
            assert window, "the xev window never appeared"
            subprocess.run(["xdotool", "windowfocus", "--sync", window], check=True, timeout=5)
            yield log
        finally:
            xev.terminate()
            xev.wait(timeout=5)


@pytest.fixture
def pressed_keys(xev_window: Path) -> Callable[[], list[str]]:
    """Callable listing the keysym of every KeyPress the xev window has received so far."""

    def keysyms() -> list[str]:
        names: list[str] = []
        awaiting_keysym = False
        for line in xev_window.read_text().splitlines():
            if line.startswith("KeyPress event"):
                awaiting_keysym = True
            elif awaiting_keysym and "keysym" in line:
                names.append(line.split("keysym", 1)[1].split(",")[1].split(")")[0].strip())
                awaiting_keysym = False
        return names

    return keysyms


async def _settled(keysyms: Callable[[], list[str]], expected: int) -> list[str]:
    """xev reports asynchronously; wait until `expected` KeyPress events have been logged."""
    for _ in range(100):
        if len(keysyms()) >= expected:
            break
        time.sleep(0.05)
    return keysyms()


class TestRealTyping:
    @pytest.mark.asyncio
    async def test_non_ascii_text_arrives_as_key_events(
        self, backend: LinuxBackend, pressed_keys: Callable[[], list[str]]
    ) -> None:
        result = await backend.type_text("a你好é")

        assert result.success is True
        assert await _settled(pressed_keys, 4) == ["a", "U4F60", "U597D", "eacute"]

    @pytest.mark.asyncio
    async def test_a_text_longer_than_one_chunk_loses_no_character(
        self, backend: LinuxBackend, pressed_keys: Callable[[], list[str]]
    ) -> None:
        result = await backend.type_text("你好世界" * 30)

        assert result.success is True
        assert len(await _settled(pressed_keys, 120)) == 120

    @pytest.mark.asyncio
    async def test_non_ascii_credential_arrives_as_key_events(
        self, backend: LinuxBackend, pressed_keys: Callable[[], list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Vault:
            def get_password(self, _label: str) -> str:
                return "密é"

        monkeypatch.setattr(
            "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault", lambda: _Vault()
        )

        result = await backend.type_credential("bank")

        assert result.success is True
        assert await _settled(pressed_keys, 2) == ["U5BC6", "eacute"]


class TestRealXdotool:
    @pytest.mark.asyncio
    async def test_mouse_move_lands_on_the_requested_point(self, backend: LinuxBackend, xev_window: Path) -> None:
        result = await backend.mouse_move(120, 80)

        located = subprocess.run(["xdotool", "getmouselocation"], capture_output=True, text=True, timeout=5)
        assert result.success is True
        assert located.stdout.startswith("x:120 y:80 ")

    @pytest.mark.asyncio
    async def test_unreachable_display_is_reported_as_a_failure(self) -> None:
        result = await LinuxBackend(display_num=_UNREACHABLE_DISPLAY).mouse_move(1, 1)

        assert result.success is False
        assert "xdotool" in (result.error or "")
