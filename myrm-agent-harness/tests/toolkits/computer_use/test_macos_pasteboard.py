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

import asyncio
import sys
import threading
import time
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
_MARKERS = ("org.nspasteboard.TransientType", "org.nspasteboard.ConcealedType")


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


class TestPasteText:
    def test_runs_snapshot_write_paste_restore_in_order(self, pb: NSPasteboard) -> None:
        from AppKit import NSPasteboardTypeString

        original = [{_TEXT: b"old", _PNG: b"\x89PNG\x00"}]
        _fill(pb, original)
        seen: list[tuple[str, set[str]]] = []

        def press() -> None:
            seen.append((str(pb.stringForType_(NSPasteboardTypeString)), _types(pb)))

        macos_pasteboard.paste_text("你好", press, concealed=True, settle_seconds=0, pb=pb)

        assert [text for text, _ in seen] == ["你好"]
        assert {_TEXT, *_MARKERS} <= seen[0][1]
        assert macos_pasteboard.snapshot(pb).items == tuple(original)

    def test_waits_for_the_target_to_read_before_restoring(self, pb: NSPasteboard) -> None:
        _fill(pb, [{_TEXT: b"old"}])
        started = time.monotonic()

        macos_pasteboard.paste_text("你好", lambda: None, settle_seconds=0.2, pb=pb)

        assert time.monotonic() - started >= 0.2

    def test_pasteboard_is_restored_when_pressing_paste_fails(self, pb: NSPasteboard) -> None:
        _fill(pb, [{_TEXT: b"old"}])

        def press() -> None:
            raise RuntimeError("no permission")

        with pytest.raises(RuntimeError, match="no permission"):
            macos_pasteboard.paste_text("你好", press, settle_seconds=0, pb=pb)

        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"old"},)

    def test_failed_write_never_pastes_and_still_restores(self, pb: NSPasteboard) -> None:
        _fill(pb, [{_TEXT: b"old"}])
        pressed: list[bool] = []

        def clear_then_fail(*_args: object, **_kwargs: object) -> int:
            pb.clearContents()
            raise RuntimeError("Failed to write text to the macOS pasteboard")

        with (
            patch.object(macos_pasteboard, "write_text", clear_then_fail),
            pytest.raises(RuntimeError, match="write text"),
        ):
            macos_pasteboard.paste_text("你好", lambda: pressed.append(True), settle_seconds=0, pb=pb)

        assert pressed == []
        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"old"},)


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

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("slow_stage", ["write", "paste"])
    async def test_cancelled_paste_still_runs_to_a_consistent_end(self, pb: NSPasteboard, slow_stage: str) -> None:
        """任务在写入或粘贴进行时被取消：目标应用仍读到文本，随后用户内容回来，不会交错残留。"""
        from AppKit import NSPasteboardTypeString

        _fill(pb, [{_TEXT: b"user text"}])
        read_by_target: list[str] = []
        finished = threading.Event()
        real_write, real_restore = macos_pasteboard.write_text, macos_pasteboard.restore

        def write(text: str, *, concealed: bool = False, pb: NSPasteboard | None = None) -> int:
            if slow_stage == "write":
                time.sleep(0.3)
            return real_write(text, concealed=concealed, pb=pb)

        def hotkey(*_keys: str) -> None:
            if slow_stage == "paste":
                time.sleep(0.3)
            read_by_target.append(str(pb.stringForType_(NSPasteboardTypeString)))

        def restore(saved: macos_pasteboard.PasteboardSnapshot, written: int | None, *, pb: NSPasteboard) -> bool:
            try:
                return real_restore(saved, written, pb=pb)
            finally:
                finished.set()

        with (
            patch.object(macos_pasteboard, "_resolve", return_value=pb),
            patch.object(macos_pasteboard, "write_text", write),
            patch.object(macos_pasteboard, "restore", restore),
            patch.object(macos_mod.macos_input, "hotkey", side_effect=hotkey),
            patch.object(macos_mod, "_PASTE_SETTLE_SECONDS", 0),
        ):
            task = asyncio.create_task(macos_mod.MacOSBackend()._paste_text("你好", concealed=True))
            await asyncio.sleep(0.1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            # 剪贴板只在工作线程结束后才读，避免测试自己与工作线程并发访问同一个 NSPasteboard。
            assert await asyncio.to_thread(finished.wait, 5)

        assert read_by_target == ["你好"]
        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"user text"},)

    def test_overlapping_pastes_are_serialized(self, pb: NSPasteboard) -> None:
        """取消后立刻重试：第二轮必须等第一轮还原完，否则会把临时文本当成用户内容。"""
        from AppKit import NSPasteboardTypeString

        _fill(pb, [{_TEXT: b"user text"}])
        order: list[str] = []

        def press(label: str) -> Callable[[], None]:
            def _press() -> None:
                order.append(f"{label}:{pb.stringForType_(NSPasteboardTypeString)}")
                time.sleep(0.15)

            return _press

        threads = [
            threading.Thread(
                target=macos_pasteboard.paste_text, args=(text, press(text)), kwargs={"settle_seconds": 0, "pb": pb}
            )
            for text in ("第一轮", "第二轮")
        ]
        for thread in threads:
            thread.start()
            time.sleep(0.05)
        for thread in threads:
            thread.join(5)

        assert order == ["第一轮:第一轮", "第二轮:第二轮"]
        assert macos_pasteboard.snapshot(pb).items == ({_TEXT: b"user text"},)
