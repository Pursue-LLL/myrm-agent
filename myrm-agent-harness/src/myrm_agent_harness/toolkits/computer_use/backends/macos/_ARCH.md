# backends/macos/

## Overview
macOS desktop backend: screencapture + Quartz CGEvent input, window-targeted capture, clipboard-paste typing, TCC permission probes.

macOS-only. Loaded by `session.py` when `detect_platform().os_type == "macos"`; `perception/macos_ax.py` also imports `permissions.py` (deeplinks) and `background.py` (EnhancedUI).

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | macOS 后端包入口（无再导出，调用方按子模块导入）。 | — |
| backend.py | Core | macOS backend — screencapture + Quartz CGEvent + NSScreen DPI + AX text; window-targeted capture (`screencapture -l`) and foreground guard via `background.py`, `check_permissions` via `permissions.py`; `set_excluded_capture_window_titles` 帷幕排除通道注入；帷幕在屏时全局 HID 坐标类指针动作（click/mouse_move/scroll/drag）fail-closed（`_pointer_occluded`，定向投递与键盘不受影响）. | ✅ |
| input.py | Core | macOS input primitives — Quartz CGEvent keyboard/mouse; PID-targeted delivery via single post router; `has_input_target()` 判定当前任务是否定向投递. | ✅ |
| pasteboard.py | Core | macOS 剪贴板借用原语 — `snapshot` 读取全部 item 的全部类型、`write_text` 写临时文本（带 `TransientType`，失败抛 `RuntimeError`）、`restore` 以 `changeCount` 守卫还原（用户在粘贴期间新复制则放弃）；`paste_text` 在一个同步函数里完成快照、写入、按键回调、等待、`finally` 还原，模块锁串行重叠调用（`backend.py:_paste_text` 只用一次 `to_thread` 调用它）；AppKit 调用期惰性导入. | ✅ |
| background.py | Core | macOS background ops — window resolve, `screencapture -l` capture, foreground guard, post-event permission, EnhancedUI (crash-contained probe); `_capture_screen_excluding_titles` Quartz below-window 截图通道（帷幕窗排除，失败降级原 screencapture 路径）. | ✅ |
| ax_scripts.py | Core | macOS accessibility probe scripts — AppleScript sources (`AX_TEXT_SCRIPT` window text, `AX_DIALOG_SCRIPT` blocking dialog) consumed by `backend.py`; parsing and timeouts stay with the callers. | — |
| permissions.py | Core | macOS TCC permission probes — Accessibility (`AXIsProcessTrusted` + osascript capability probe), Screen Recording (`CGPreflightScreenCaptureAccess`), optional capture-usability probe, post-event access, System Settings deeplinks (`_MACOS_DEEPLINKS`, also consumed by `perception/macos_ax.py`); consumed by `backend.py` `check_permissions`. | ✅ |
