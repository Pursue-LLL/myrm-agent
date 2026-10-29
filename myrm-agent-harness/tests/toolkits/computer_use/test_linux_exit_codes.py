"""Linux backend must surface failing xdotool/xclip invocations instead of reporting success.

Uses real subprocesses: an empty PATH makes the shell return 127 for every tool, and
fake xclip/xdotool scripts exercise the clipboard restore with genuine exit codes.
"""

from __future__ import annotations

import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="relies on /bin/sh and POSIX PATH lookup")

_FAKE_XCLIP = """#!/bin/sh
case "$*" in *-o*) cat "$CLIP"; exit 0;; esac
cat > "$CLIP"
"""

_FAKE_XDOTOOL = """#!/bin/sh
if [ "$1" = key ]; then cat "$CLIP" >> "$SEEN"; exit "${XDOTOOL_RC:-0}"; fi
exit 0
"""


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend(display_num=1)


@pytest.fixture
def empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def fake_x_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """xclip/xdotool stand-ins; CLIP is the clipboard, SEEN records what Ctrl+V would paste."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("xclip", _FAKE_XCLIP), ("xdotool", _FAKE_XDOTOOL)):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    clip, seen = tmp_path / "clip", tmp_path / "seen"
    clip.write_text("old")
    seen.write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("CLIP", str(clip))
    monkeypatch.setenv("SEEN", str(seen))
    return {"clip": clip, "seen": seen}


_ACTIONS: dict[str, Callable[[LinuxBackend], Awaitable[ActionResult]]] = {
    "type_text_ascii": lambda b: b.type_text("abc"),
    "key": lambda b: b.key("ctrl+c"),
    "mouse_move": lambda b: b.mouse_move(1, 2),
    "click": lambda b: b.click(1, 2),
    "click_with_modifier": lambda b: b.click(1, 2, modifiers=["ctrl"]),
    "scroll": lambda b: b.scroll(1, 2, "down"),
    "drag": lambda b: b.drag(1, 2, 3, 4),
}


class TestMissingTools:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", sorted(_ACTIONS))
    async def test_input_action_fails_when_xdotool_is_missing(
        self, backend: LinuxBackend, empty_path: None, action: str
    ) -> None:
        result = await _ACTIONS[action](backend)

        assert result.success is False
        assert "xdotool" in (result.error or "")

    @pytest.mark.asyncio
    async def test_non_ascii_text_fails_when_xclip_is_missing(self, backend: LinuxBackend, empty_path: None) -> None:
        result = await backend.type_text("你好")

        assert result.success is False
        assert "xclip" in (result.error or "")


class TestClipboardPaste:
    @pytest.mark.asyncio
    async def test_target_sees_the_text_and_the_clipboard_comes_back(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        result = await backend.type_text("你好")

        assert result.success is True
        assert fake_x_tools["seen"].read_text() == "你好"
        assert fake_x_tools["clip"].read_text() == "old"

    @pytest.mark.asyncio
    async def test_failed_paste_keystroke_is_reported_and_the_clipboard_still_comes_back(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDOTOOL_RC", "1")

        result = await backend.type_text("你好")

        assert result.success is False
        assert "xdotool" in (result.error or "")
        assert fake_x_tools["clip"].read_text() == "old"
