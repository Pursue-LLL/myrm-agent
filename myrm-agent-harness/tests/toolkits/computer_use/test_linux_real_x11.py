"""LinuxBackend against a real X server, the real xdotool/xclip and a real Tk text widget.

The fake-tool suites cannot show what the genuine binaries do, and a key-event log cannot show whether text
arrived intact: xdotool reported success for characters the application never received. So the ruler is a
Tk `Text` widget whose content is compared character for character with what was sent.

CI runs this file under `xvfb-run`. It moves the pointer, types and borrows the clipboard, so it only runs when
MYRM_REAL_X11_TESTS=1 is set: never on a developer's own desktop session.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend

# The system interpreter carries python3-tk; a managed interpreter may not.
_TK_PYTHON = "/usr/bin/python3"


def _tk_available() -> bool:
    if not os.path.exists(_TK_PYTHON):
        return False
    probe = subprocess.run([_TK_PYTHON, "-c", "import tkinter"], capture_output=True, timeout=30, check=False)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not (
        sys.platform.startswith("linux")
        and os.environ.get("MYRM_REAL_X11_TESTS") == "1"
        and os.environ.get("DISPLAY")
        and shutil.which("xdotool")
        and shutil.which("xclip")
        and _tk_available()
    ),
    reason="needs MYRM_REAL_X11_TESTS=1, a DISPLAY (xvfb-run), xdotool, xclip and python3-tk",
)

_UNREACHABLE_DISPLAY = 987
_WINDOW_NAME = "TkRuler"

# Dumps the Text content to a file every 50 ms; the test reads it back.
_TK_APP = """
import os, sys, tkinter
out = sys.argv[1]
root = tkinter.Tk()
root.title("TkRuler")
root.geometry("600x300+0+0")
text = tkinter.Text(root, wrap="word")
text.pack(fill="both", expand=True)
text.focus_force()
def dump():
    with open(out + ".tmp", "w", encoding="utf-8") as sink:
        sink.write(text.get("1.0", "end-1c"))
    os.replace(out + ".tmp", out)
    root.after(50, dump)
dump()
root.mainloop()
"""

# 120 distinct CJK characters: a dropped or substituted one cannot hide behind a repeating pattern.
_CJK = "".join(chr(0x4E00 + 37 * i) for i in range(120))
_ASCII_MIX = "Hello, World! @#$%^&*()_+-=[]{}|;':\",./<>?`~ 0123456789 \\ end"


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend()


@pytest.fixture
def ruler(tmp_path: Path) -> Iterator[Callable[[], str]]:
    """A focused Tk text window; yields a callable returning its current content."""
    out = tmp_path / "content.txt"
    out.write_text("")
    app = subprocess.Popen([_TK_PYTHON, "-c", _TK_APP, str(out)])
    try:
        window = ""
        for _ in range(200):
            found = subprocess.run(
                ["xdotool", "search", "--name", _WINDOW_NAME], capture_output=True, text=True, timeout=5, check=False
            )
            window = found.stdout.split()[0] if found.stdout.split() else ""
            if window:
                break
            time.sleep(0.1)
        assert window, "the Tk window never appeared"
        subprocess.run(["xdotool", "windowfocus", "--sync", window], check=True, timeout=5)
        yield lambda: out.read_text(encoding="utf-8")
    finally:
        app.terminate()
        app.wait(timeout=5)


async def _content_after(ruler: Callable[[], str], expected: str) -> str:
    """The widget updates asynchronously: wait for the expected content, return whatever is there at the end."""
    for _ in range(200):
        if ruler() == expected:
            break
        await asyncio.sleep(0.05)
    return ruler()


def _set_clipboard(text: str) -> None:
    # xclip forks a selection owner that keeps its inherited pipes open, so nothing may be captured.
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=True,
    )


def _clipboard() -> str:
    read = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=10, check=False)
    return read.stdout.decode()


class TestRealTextEntry:
    @pytest.mark.asyncio
    async def test_ascii_with_punctuation_arrives_exactly(
        self, backend: LinuxBackend, ruler: Callable[[], str]
    ) -> None:
        result = await backend.type_text(_ASCII_MIX)

        assert result.success is True
        assert await _content_after(ruler, _ASCII_MIX) == _ASCII_MIX

    @pytest.mark.asyncio
    async def test_cjk_arrives_exactly_every_round(self, backend: LinuxBackend, ruler: Callable[[], str]) -> None:
        expected = ""
        for _ in range(5):
            expected += _CJK

            result = await backend.type_text(_CJK)

            assert result.success is True
            assert await _content_after(ruler, expected) == expected

    @pytest.mark.asyncio
    async def test_multiline_mixed_text_arrives_exactly(self, backend: LinuxBackend, ruler: Callable[[], str]) -> None:
        text = "第一行 first\n第二行 café\n\n  最后一行, with punctuation!"

        result = await backend.type_text(text)

        assert result.success is True
        assert await _content_after(ruler, text) == text

    @pytest.mark.asyncio
    async def test_host_pinned_non_utf8_locale_does_not_matter(
        self, backend: LinuxBackend, ruler: Callable[[], str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LC_ALL", "C")

        result = await backend.type_text(_CJK)

        assert result.success is True
        assert await _content_after(ruler, _CJK) == _CJK

    @pytest.mark.asyncio
    async def test_the_users_clipboard_survives_a_paste(self, backend: LinuxBackend, ruler: Callable[[], str]) -> None:
        _set_clipboard("what the user copied")

        result = await backend.type_text(_CJK)

        assert result.success is True
        assert await _content_after(ruler, _CJK) == _CJK
        assert _clipboard() == "what the user copied"

    @pytest.mark.asyncio
    async def test_non_ascii_credential_arrives_exactly_and_leaves_no_trace_on_the_clipboard(
        self, backend: LinuxBackend, ruler: Callable[[], str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Vault:
            def get_password(self, _label: str) -> str:
                return "密码é-S3cr3t"

        monkeypatch.setattr(
            "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault", lambda: _Vault()
        )
        _set_clipboard("what the user copied")

        result = await backend.type_credential("bank")

        assert result.success is True
        assert await _content_after(ruler, "密码é-S3cr3t") == "密码é-S3cr3t"
        assert _clipboard() == "what the user copied"


class TestRealXdotool:
    @pytest.mark.asyncio
    async def test_mouse_move_lands_on_the_requested_point(
        self, backend: LinuxBackend, ruler: Callable[[], str]
    ) -> None:
        result = await backend.mouse_move(120, 80)

        located = subprocess.run(
            ["xdotool", "getmouselocation"], capture_output=True, text=True, timeout=5, check=False
        )
        assert result.success is True
        assert located.stdout.startswith("x:120 y:80 ")

    @pytest.mark.asyncio
    async def test_unreachable_display_is_reported_as_a_failure(self) -> None:
        result = await LinuxBackend(display_num=_UNREACHABLE_DISPLAY).mouse_move(1, 1)

        assert result.success is False
        assert "xdotool" in (result.error or "")
