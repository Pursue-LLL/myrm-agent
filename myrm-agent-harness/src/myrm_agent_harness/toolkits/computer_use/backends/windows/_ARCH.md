# backends/windows/

## Overview
Windows desktop backend: mss + pyautogui + ctypes/user32 + uiautomation, SendInput Unicode typing, overlay-aware capture.

Windows-only. Loaded by `session.py` when `detect_platform().os_type == "windows"`; every Win32 / uiautomation call resolves at call time so the modules import on any OS.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Windows 后端包入口（无再导出，调用方按子模块导入）。 | — |
| backend.py | Core | Windows backend — mss + pyautogui + ctypes/user32 + uiautomation; `set_excluded_capture_window_titles` 帷幕排除注入；帷幕在屏时全局指针动作 fail-closed（`_pointer_occluded`）；全屏截图合并 `SNAPSHOT_ONLY_EXCLUDED_CAPTURE_TITLES`（视觉审批高亮）. | ✅ |
| text_io.py | Core | Windows 文本桥 — `type_unicode_text`（`SendInput` Unicode 键事件逐 UTF-16 代码单元输入，换行折成一次 Return，分块发送，不碰剪贴板；UIPI 拦截不可检测）、`extract_window_text`（uiautomation 前台窗口文本，递归收集有深度/数量上限）；Win32 与 uiautomation 调用期解析，跨平台可导入. | ✅ |
| background.py | Core | Windows overlay ops — `_lowest_overlay_hwnd` title 探测；`_capture_screen_excluding_titles` mss 路径（帷幕 WDA 已由桌面端设置）. | ✅ |
