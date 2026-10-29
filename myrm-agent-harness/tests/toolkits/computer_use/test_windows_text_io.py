"""Tests for windows_text_io.type_unicode_text (SendInput Unicode typing).

Covers:
- the INPUT structure has the real Win32 size SendInput validates (fixed-width fields)
- characters become Unicode key events, non-BMP characters become surrogate pairs
- every line-break style is typed as exactly one Return key, also across chunk boundaries
- text is sent in chunks with a pause between them, never after the last one
- an incomplete insertion raises instead of reporting success
- the SendInput prototype is declared on a private library instance, not the shared ctypes.windll
- platforms without ctypes.WinDLL fail loudly
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.backends import windows_text_io
from myrm_agent_harness.toolkits.computer_use.backends.windows_text_io import type_unicode_text

_UNICODE = 0x0004
_KEYUP = 0x0002
_RETURN = 0x0D


@pytest.fixture(autouse=True)
def _fresh_user32_cache():
    """The loader is cached; keep one test's double from leaking into the next."""
    windows_text_io._user32.cache_clear()
    yield
    windows_text_io._user32.cache_clear()


class _SendInputRecorder:
    """A user32 double whose SendInput decodes the INPUT array the way Windows would read it."""

    def __init__(self, *, accept: int | None = None) -> None:
        self.user32 = MagicMock()
        self.user32.SendInput.side_effect = self._send_input
        self.calls: list[list[tuple[int, int, int]]] = []
        self.cb_sizes: list[int] = []
        self._accept = accept

    def _send_input(self, count: int, events, cb_size: int) -> int:
        self.cb_sizes.append(cb_size)
        self.calls.append([(events[i].ki.wVk, events[i].ki.wScan, events[i].ki.dwFlags) for i in range(count)])
        assert all(events[i].type == 1 for i in range(count)), "every event must be INPUT_KEYBOARD"
        return count if self._accept is None else self._accept

    def run(self, text: str, delay_ms: int = 0, chunk_size: int = 50) -> None:
        with patch.object(ctypes, "WinDLL", return_value=self.user32, create=True):
            type_unicode_text(text, delay_ms, chunk_size)

    @property
    def events(self) -> list[tuple[int, int, int]]:
        return [event for call in self.calls for event in call]


class TestInputLayout:
    def test_input_has_the_win32_size(self) -> None:
        assert ctypes.sizeof(windows_text_io._Input) == 40

    def test_cb_size_passed_to_send_input_matches_the_structure(self) -> None:
        recorder = _SendInputRecorder()
        recorder.run("中")
        assert recorder.cb_sizes == [40]


class TestKeyEvents:
    def test_bmp_character_is_one_unicode_key_down_and_up(self) -> None:
        recorder = _SendInputRecorder()
        recorder.run("中")
        assert recorder.events == [(0, 0x4E2D, _UNICODE), (0, 0x4E2D, _UNICODE | _KEYUP)]

    def test_non_bmp_character_is_sent_as_a_surrogate_pair(self) -> None:
        recorder = _SendInputRecorder()
        recorder.run("\U0001f600")
        assert recorder.events == [
            (0, 0xD83D, _UNICODE),
            (0, 0xD83D, _UNICODE | _KEYUP),
            (0, 0xDE00, _UNICODE),
            (0, 0xDE00, _UNICODE | _KEYUP),
        ]

    @pytest.mark.parametrize("line_break", ["\n", "\r", "\r\n"])
    def test_every_line_break_style_is_one_return_key(self, line_break: str) -> None:
        recorder = _SendInputRecorder()
        recorder.run(f"中{line_break}文")
        assert recorder.events == [
            (0, 0x4E2D, _UNICODE),
            (0, 0x4E2D, _UNICODE | _KEYUP),
            (_RETURN, 0, 0),
            (_RETURN, 0, _KEYUP),
            (0, 0x6587, _UNICODE),
            (0, 0x6587, _UNICODE | _KEYUP),
        ]

    def test_crlf_split_by_a_chunk_boundary_is_still_one_return(self) -> None:
        recorder = _SendInputRecorder()
        recorder.run("中\r\n文", chunk_size=2)
        assert [event for event in recorder.events if event[0] == _RETURN] == [(_RETURN, 0, 0), (_RETURN, 0, _KEYUP)]

    def test_empty_text_sends_nothing(self) -> None:
        recorder = _SendInputRecorder()
        recorder.run("")
        assert recorder.calls == []


class TestChunking:
    def test_text_is_sent_in_chunks_with_a_pause_between_them(self) -> None:
        recorder = _SendInputRecorder()
        with patch.object(windows_text_io.time, "sleep") as sleep:
            recorder.run("中" * 120, delay_ms=12, chunk_size=50)
        assert [len(call) // 2 for call in recorder.calls] == [50, 50, 20]
        assert [call.args[0] for call in sleep.call_args_list] == [0.012, 0.012]

    def test_single_chunk_never_sleeps(self) -> None:
        recorder = _SendInputRecorder()
        with patch.object(windows_text_io.time, "sleep") as sleep:
            recorder.run("中文", delay_ms=12, chunk_size=50)
        sleep.assert_not_called()


class TestFailure:
    def test_incomplete_insertion_raises(self) -> None:
        recorder = _SendInputRecorder(accept=0)
        with patch.object(ctypes, "get_last_error", return_value=5, create=True), pytest.raises(OSError) as error:
            recorder.run("中")
        assert "inserted 0 of 2 key events" in str(error.value)
        assert "last error 5" in str(error.value)

    def test_platform_without_win_dll_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(ctypes, "WinDLL", raising=False)
        with pytest.raises(AttributeError):
            type_unicode_text("中", 0, 50)


class TestPrototype:
    def test_send_input_prototype_is_declared_on_a_private_library_instance(self) -> None:
        recorder = _SendInputRecorder()
        windll = MagicMock()
        with (
            patch.object(ctypes, "windll", windll, create=True),
            patch.object(ctypes, "WinDLL", return_value=recorder.user32, create=True) as win_dll,
        ):
            type_unicode_text("中", 0, 50)
        win_dll.assert_called_once_with("user32", use_last_error=True)
        assert recorder.user32.SendInput.argtypes == (
            wintypes.UINT,
            ctypes.POINTER(windows_text_io._Input),
            ctypes.c_int,
        )
        assert recorder.user32.SendInput.restype is wintypes.UINT
        windll.user32.SendInput.assert_not_called()
