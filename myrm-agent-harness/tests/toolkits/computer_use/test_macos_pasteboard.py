"""macos_pasteboard 单测 — 真实 NSPasteboard（独立名称剪贴板）上的快照、写入、守卫还原。

[INPUT]
- backends.macos_pasteboard (POS: NSPasteboard 全类型快照、临时写入文本、带守卫还原)
- backends.macos::MacOSBackend (POS: macOS 平台 backend 实现)

[OUTPUT]
- 多 item 多类型往返、空剪贴板、临时标记、凭证标记、写入失败抛错、changeCount 守卫，以及
  `MacOSBackend._paste_text` 在真实剪贴板上的端到端（用读剪贴板的替身 Cmd+V 代替目标应用）的回归保护

[POS]
仅 darwin 运行；全部操作发生在 `pasteboardWithUniqueName()` 的私有剪贴板上，不触碰用户的通用剪贴板，
也不投递任何按键事件。
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.computer_use.backends import macos as macos_mod
from myrm_agent_harness.toolkits.computer_use.backends import macos_pasteboard

if TYPE_CHECKING:
    from AppKit import NSPasteboard

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="NSPasteboard is only available on macOS")

_PNG = "public.png"
_CUSTOM = "com.example.custom"
_TEXT = "public.utf8-plain-text"


@pytest.fixture()
def pb() -> Iterator[NSPasteboard]:
    from AppKit import NSPasteboard

    board = NSPasteboard.pasteboardWithUniqueName()
    yield board
    board.releaseGlobally()


def _fill(board: NSPasteboard, items: list[dict[str, bytes]]) -> None:
    """用给定 {类型: 字节} 列表写满剪贴板（独立于被测的 restore，避免自证）。"""
    from AppKit import NSPasteboardItem
    from Foundation import NSData

    objects = []
    for payload in items:
        item = NSPasteboardItem.alloc().init()
        for type_name, data in payload.items():
            assert item.setData_forType_(NSData.dataWithBytes_length_(data, len(data)), type_name)
        objects.append(item)
    board.clearContents()
    assert board.writeObjects_(objects)


def _types(board: NSPasteboard) -> set[str]:
    return {str(t) for t in board.types() or []}


class TestSnapshotRestore:
    def test_multi_item_multi_type_roundtrip_is_byte_exact(self, pb: NSPasteboard) -> None:
        original = [
            {_TEXT: b"hello", _PNG: b"\x89PNG\x00\xff", _CUSTOM: b"xyz"},
            {_TEXT: "第二项".encode()},
        ]
        _fill(pb, original)
        saved = macos_pasteboard.snapshot(pb)

        written = macos_pasteboard.write_text("你好", pb=pb)
        assert macos_pasteboard.restore(saved, written, pb=pb) is True

        assert macos_pasteboard.snapshot(pb).items == tuple(original)

    def test_empty_pasteboard_is_restored_to_empty(self, pb: NSPasteboard) -> None:
        pb.clearContents()
        saved = macos_pasteboard.snapshot(pb)
        assert saved.items == ()

        written = macos_pasteboard.write_text("你好", pb=pb)
        assert macos_pasteboard.restore(saved, written, pb=pb) is True

        assert macos_pasteboard.snapshot(pb).items == ()

    def test_restore_yields_to_a_newer_copy_by_the_user(self, pb: NSPasteboard) -> None:
        _fill(pb, [{_TEXT: b"old"}])
        saved = macos_pasteboard.snapshot(pb)
        written = macos_pasteboard.write_text("你好", pb=pb)

        _fill(pb, [{_TEXT: b"copied meanwhile"}])

        assert macos_pasteboard.restore(saved, written, pb=pb) is False
        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"copied meanwhile"},)

    def test_restore_without_written_count_restores_unconditionally(self, pb: NSPasteboard) -> None:
        _fill(pb, [{_TEXT: b"old"}])
        saved = macos_pasteboard.snapshot(pb)
        pb.clearContents()

        assert macos_pasteboard.restore(saved, None, pb=pb) is True

        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"old"},)


class TestWriteText:
    def test_text_is_readable_and_marked_transient(self, pb: NSPasteboard) -> None:
        from AppKit import NSPasteboardTypeString

        macos_pasteboard.write_text("你好 \N{GRINNING FACE}", pb=pb)

        assert pb.stringForType_(NSPasteboardTypeString) == "你好 \N{GRINNING FACE}"
        assert "org.nspasteboard.TransientType" in _types(pb)
        assert "org.nspasteboard.ConcealedType" not in _types(pb)

    def test_credential_text_is_also_marked_concealed(self, pb: NSPasteboard) -> None:
        macos_pasteboard.write_text("密钥", concealed=True, pb=pb)

        assert {"org.nspasteboard.TransientType", "org.nspasteboard.ConcealedType"} <= _types(pb)

    def test_returns_the_change_count_after_the_write(self, pb: NSPasteboard) -> None:
        assert macos_pasteboard.write_text("你好", pb=pb) == pb.changeCount()

    def test_failed_write_raises_instead_of_pasting_stale_content(self) -> None:
        class RejectingPasteboard:
            def clearContents(self) -> int:  # noqa: N802 - mirrors NSPasteboard
                return 0

            def writeObjects_(self, _objects: list[object]) -> bool:  # noqa: N802
                return False

        with pytest.raises(RuntimeError, match="write text"):
            macos_pasteboard.write_text("你好", pb=RejectingPasteboard())


class TestPasteTextEndToEnd:
    """真实剪贴板上跑完整的 `_paste_text`：Cmd+V 的替身像目标应用那样读剪贴板，不投递任何按键。"""

    @staticmethod
    async def _paste(
        pb: NSPasteboard, text: str, *, concealed: bool, during_paste: Callable[[], None] | None = None
    ) -> tuple[str, set[str]]:
        """返回「目标应用在 Cmd+V 时读到的文本与剪贴板类型」。"""
        from AppKit import NSPasteboardTypeString

        seen: list[tuple[str, set[str]]] = []

        def fake_hotkey(*_keys: str) -> None:
            seen.append((str(pb.stringForType_(NSPasteboardTypeString)), _types(pb)))
            if during_paste is not None:
                during_paste()

        with (
            patch.object(macos_pasteboard, "_resolve", return_value=pb),
            patch.object(macos_mod.macos_input, "hotkey", side_effect=fake_hotkey),
            patch.object(macos_mod, "_PASTE_SETTLE_SECONDS", 0),
        ):
            await macos_mod.MacOSBackend()._paste_text(text, concealed=concealed)
        return seen[0]

    @pytest.mark.asyncio()
    async def test_target_reads_the_text_and_the_user_content_comes_back(self, pb: NSPasteboard) -> None:
        original = [{_TEXT: b"old", _PNG: b"\x89PNG\x00"}, {_TEXT: b"second"}]
        _fill(pb, original)

        text, types = await self._paste(pb, "你好", concealed=True)

        assert text == "你好"
        assert {"org.nspasteboard.TransientType", "org.nspasteboard.ConcealedType"} <= types
        assert macos_pasteboard.snapshot(pb).items == tuple(original)

    @pytest.mark.asyncio()
    async def test_a_copy_made_during_the_paste_is_not_overwritten(self, pb: NSPasteboard) -> None:
        _fill(pb, [{_TEXT: b"old"}])

        await self._paste(pb, "你好", concealed=False, during_paste=lambda: _fill(pb, [{_TEXT: b"copied meanwhile"}]))

        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"copied meanwhile"},)
