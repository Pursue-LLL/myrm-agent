# app 模块架构

[INPUT]
- commands / runtime / config / utils 各模块
- Tauri Builder 插件注册表

[OUTPUT]
- run(): 应用主循环、IPC handler、托盘、优雅停机

[POS]
Tauri 应用组装层；main.rs 唯一委托目标。

## 架构概述

Tauri 应用组装层：插件注册、全局快捷键分发、`setup` 钩子、窗口事件、IPC handler 清单、统一 IPC sender gate、托盘与优雅停机。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `mod.rs` | `run()`：Builder 链、基于 `command_registry_macro.in` 的 `generate_handler`、帷幕看板与审批高亮自定义协议注册、退出优雅停机 |
| `setup.rs` | `on_setup` / `on_window_event`：配置、Sidecar 自启（Next 始终；Python 在 Remote 跟随态 defer）、托盘、隐私帷幕 watcher spawn；启动失败 emit `backend-start-failed` / `frontend-start-failed`；后端启动成功后经 `runtime::spawn_backend_monitors` 统一挂载 watchdog+wake。`on_window_event` 的应用级窗口策略（关闭到托盘、窗口销毁即优雅停机）不管辖帷幕与审批高亮覆盖层（`governs_app_lifecycle`）：它们按需建、用完即销，被拦成隐藏窗会翻转 Dock 策略，被销毁则会被误当作应用退出 |
| `shortcut_handler.rs` | 全局快捷键事件分发 |
| `linux_gpu.rs` | Linux NVIDIA + Wayland WebKitGTK 兼容 |
| `menu.rs` | 原生应用主菜单与 Edit 快捷键桥接（macOS AppKit / Win32 Responder Chain） |
| `tray.rs` | 系统托盘菜单、状态 tooltip、隐私帷幕切换项、IPC `set_tray_status` |
| `lifecycle.rs` | 优雅停机：`SHUTDOWN_INITIATED` 防重入 + `graceful_stop_backend`（停 monitors → 服务端 drain → 等待自退 → 兜底强杀）+ Sidecar 有序关闭；后端停止后代解锁租约仍未交还则 `relock_outstanding_lease` 兜底回锁（帷幕窗口随进程消失，不能留下解锁态桌面） |

## 依赖

- `runtime` / `commands` / `config` / `utils`
