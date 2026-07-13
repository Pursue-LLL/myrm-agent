# app 模块架构

## 架构概述

Tauri 应用组装层：插件注册、全局快捷键分发、`setup` 钩子、窗口事件、IPC handler 清单。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `mod.rs` | `run()`：Builder 链、`generate_handler`（叶子模块路径）、退出优雅停机 |
| `setup.rs` | `on_setup` / `on_window_event`：配置、Sidecar 自启（Python + Next 始终）、托盘；启动失败 emit `backend-start-failed` / `frontend-start-failed` |
| `shortcut_handler.rs` | 全局快捷键事件分发 |
| `linux_gpu.rs` | Linux NVIDIA + Wayland WebKitGTK 兼容 |

## 依赖

- `runtime` / `commands` / `config` / `lifecycle` / `tray` / `utils`
