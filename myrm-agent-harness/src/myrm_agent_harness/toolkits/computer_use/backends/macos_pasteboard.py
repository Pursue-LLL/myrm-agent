"""macOS 剪贴板借用原语 — NSPasteboard 全类型快照、临时写入文本、带守卫还原。

非 ASCII 文本经 Cmd+V 粘贴输入时需要临时占用剪贴板；本模块保证占用前后用户的
剪贴板内容（文本、图片、文件等全部类型）原样回到用户手里，且临时文本不进入
剪贴板历史工具。

[INPUT]
- 无项目内依赖（AppKit/Foundation 经 pyobjc，随 computer-use extra 安装，调用期惰性导入）

[OUTPUT]
- PasteboardSnapshot: 剪贴板全部 item 的全部类型字节快照
- snapshot / write_text / restore: 快照、写入临时文本（失败即抛错）、changeCount 守卫还原
- paste_text: 同步编排「快照、写入、粘贴、等待、还原」，调用方被取消时仍完整跑完

[POS]
macOS 剪贴板借用原语。仅被 backends/macos.py 的 `_paste_text` 引用。
所有函数可注入 `pb`（NSPasteboard），默认操作通用剪贴板；测试注入独立名称剪贴板。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from AppKit import NSPasteboard

logger = logging.getLogger(__name__)

# nspasteboard.org 约定：剪贴板历史工具应忽略带这两个标记的内容。
_TRANSIENT_TYPE = "org.nspasteboard.TransientType"
_CONCEALED_TYPE = "org.nspasteboard.ConcealedType"

# 同一时刻只允许一轮借用：取消后立刻重试时，新一轮必须等上一轮还原完，否则会把我方临时文本当成用户内容快照下来。
_PASTE_LOCK = threading.Lock()


@dataclass(frozen=True)
class PasteboardSnapshot:
    """剪贴板内容快照：每个 item 一份 {类型: 字节}，空剪贴板为空元组。"""

    items: tuple[dict[str, bytes], ...]


def _resolve(pb: NSPasteboard | None) -> NSPasteboard:
    from AppKit import NSPasteboard

    return pb if pb is not None else NSPasteboard.generalPasteboard()


def snapshot(pb: NSPasteboard | None = None) -> PasteboardSnapshot:
    """读取剪贴板全部 item 的全部类型；读不出数据的类型跳过。"""
    items: list[dict[str, bytes]] = []
    for item in _resolve(pb).pasteboardItems() or []:
        payload = {str(t): bytes(data) for t in item.types() if (data := item.dataForType_(t)) is not None}
        if payload:
            items.append(payload)
    return PasteboardSnapshot(tuple(items))


def write_text(text: str, *, concealed: bool = False, pb: NSPasteboard | None = None) -> int:
    """用文本替换剪贴板并返回写入后的 changeCount；写入失败抛 RuntimeError。

    临时文本总带 TransientType；concealed=True（凭证）再带 ConcealedType。
    """
    from AppKit import NSPasteboardItem, NSPasteboardTypeString
    from Foundation import NSData

    board = _resolve(pb)
    item = NSPasteboardItem.alloc().init()
    markers = (_TRANSIENT_TYPE, _CONCEALED_TYPE) if concealed else (_TRANSIENT_TYPE,)
    if not item.setString_forType_(text, NSPasteboardTypeString) or not all(
        item.setData_forType_(NSData.data(), marker) for marker in markers
    ):
        raise RuntimeError("Failed to prepare text for the macOS pasteboard")
    board.clearContents()
    if not board.writeObjects_([item]):
        raise RuntimeError("Failed to write text to the macOS pasteboard")
    return int(board.changeCount())


def restore(saved: PasteboardSnapshot, written_change_count: int | None, *, pb: NSPasteboard | None = None) -> bool:
    """还原快照；剪贴板在我方写入后又被改动（用户新复制）则放弃，返回是否已还原。

    written_change_count 为 None 表示写入未完成，没有需要保护的我方内容，直接还原。
    """
    from AppKit import NSPasteboardItem
    from Foundation import NSData

    board = _resolve(pb)
    if written_change_count is not None and board.changeCount() != written_change_count:
        return False
    restored = []
    for payload in saved.items:
        item = NSPasteboardItem.alloc().init()
        for type_name, data in payload.items():
            item.setData_forType_(NSData.dataWithBytes_length_(data, len(data)), type_name)
        restored.append(item)
    board.clearContents()
    if restored and not board.writeObjects_(restored):
        logger.warning("Failed to restore the macOS pasteboard after pasting text")
        return False
    return True


def paste_text(
    text: str,
    press_paste: Callable[[], None],
    *,
    concealed: bool = False,
    settle_seconds: float,
    pb: NSPasteboard | None = None,
) -> None:
    """借用剪贴板粘贴文本：快照、写入、`press_paste()`、等待目标应用读取、还原。

    整个过程是一个同步函数，由调用方放进单个工作线程：异步调用方被取消时线程仍会跑完，
    目标应用读到的一定是我们写的文本，随后用户的内容一定回来，不会出现写入与还原交错；
    进程内的并发调用经 `_PASTE_LOCK` 串行。
    """
    with _PASTE_LOCK:
        saved = snapshot(pb)
        written: int | None = None
        try:
            written = write_text(text, concealed=concealed, pb=pb)
            press_paste()
            time.sleep(settle_seconds)
        finally:
            restore(saved, written, pb=pb)
