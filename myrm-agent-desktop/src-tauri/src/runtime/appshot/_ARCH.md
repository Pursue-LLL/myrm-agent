# appshot 子模块架构

[INPUT]
- config::ConfigManager（POS: appshot_excluded_apps 隐私黑名单）
- capture_macos / capture_windows 平台实现

[OUTPUT]
- IPC: appshot-captured / appshot-blocked / voice-ptt-*

[POS]
全局快捷键截屏与 Voice PTT 唯一入口。

## 架构概述

全局快捷键截屏与 Voice PTT。平台实现分文件，共享逻辑在 `common.rs`。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `mod.rs` | 快捷键入口、IPC emit、窗口 toggle | ✅ |
| `common.rs` | 时间戳、隐私黑名单、JPEG 压缩 | — |
| `capture_macos.rs` | macOS screencapture + AppleScript AX | — |
| `capture_windows.rs` | Windows PrintWindow + UI Automation | — |
