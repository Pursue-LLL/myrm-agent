"""LinuxBackend against a real X server with the real xdotool and xclip.

The fake-tool suites cannot show what the genuine binaries do (exit codes, how an empty clipboard
reads back), so CI runs this file under `xvfb-run`. It moves the pointer and rewrites the clipboard,
so it only runs when MYRM_REAL_X11_TESTS=1 is set: never on a developer's own desktop session.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend

pytestmark = pytest.mark.skipif(
    not (
        sys.platform.startswith("linux")
        and os.environ.get("MYRM_REAL_X11_TESTS") == "1"
        and os.environ.get("DISPLAY")
        and shutil.which("xdotool")
        and shutil.which("xclip")
    ),
    reason="needs MYRM_REAL_X11_TESTS=1, a DISPLAY (xvfb-run) and xdotool + xclip",
)

_UNREACHABLE_DISPLAY = 987


def _clipboard() -> str:
    return subprocess.run(
        ["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5, check=False
    ).stdout


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend()


class TestRealXdotool:
    @pytest.mark.asyncio
    async def test_mouse_move_lands_on_the_requested_point(self, backend: LinuxBackend) -> None:
        result = await backend.mouse_move(120, 80)

        located = subprocess.run(["xdotool", "getmouselocation"], capture_output=True, text=True, timeout=5)
        assert result.success is True
        assert located.stdout.startswith("x:120 y:80 ")

    @pytest.mark.asyncio
    async def test_unreachable_display_is_reported_as_a_failure(self) -> None:
        result = await LinuxBackend(display_num=_UNREACHABLE_DISPLAY).mouse_move(1, 1)

        assert result.success is False
        assert "xdotool" in (result.error or "")


class TestRealXclip:
    @pytest.mark.asyncio
    async def test_written_text_reads_back(self, backend: LinuxBackend) -> None:
        await backend._xclip_write("你好 clipboard")

        assert _clipboard() == "你好 clipboard"

    @pytest.mark.asyncio
    async def test_writing_an_empty_string_clears_the_clipboard(self, backend: LinuxBackend) -> None:
        await backend._xclip_write("a secret")

        await backend._xclip_write("")

        assert _clipboard() == ""

    @pytest.mark.asyncio
    async def test_pasting_non_ascii_text_restores_the_previous_clipboard(self, backend: LinuxBackend) -> None:
        await backend._xclip_write("previous")

        result = await backend.type_text("你好")

        assert result.success is True
        assert _clipboard() == "previous"

    @pytest.mark.asyncio
    async def test_pasting_into_an_empty_clipboard_leaves_it_empty(self, backend: LinuxBackend) -> None:
        await backend._xclip_write("")

        result = await backend.type_text("你好")

        assert result.success is True
        assert _clipboard() == ""
