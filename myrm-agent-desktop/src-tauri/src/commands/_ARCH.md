# commands 模块架构

[INPUT]
- runtime / agent_runner_rpc / sessions / permissions / config / utils

[OUTPUT]
- Tauri invoke IPC 命令（前端 ↔ Rust）

[POS]
Tauri IPC 薄封装层；业务逻辑委托 runtime 与子模块。

> 注：命令调度前统一经过 `ipc_security` sender gate（app 层），并对高敏命令采用“短时意图票据 + 原生确认（多语言文案 + 主窗口 parent 绑定）”双校验（如数据迁移/数据库导出）。

## 架构概述

Tauri `invoke` IPC 命令层：薄封装转发到 runtime、agent_runner_rpc、sessions、utils。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 子模块聚合与 re-export | — |
| `config.rs` | 核心 | 系统配置读写、快捷键、数据目录迁移 | — |
| `agent/` | 核心 | CLI Agent IPC → [agent/_ARCH.md](agent/_ARCH.md) | — |
| `power.rs` | 核心 | 电源锁 IPC（委托 `utils/power`） | — |
| `screen_lock.rs` | 核心 | 锁屏 IPC（委托 `utils/screen_lock`） | — |
| `pet_overlay.rs` | 核心 | 桌面宠物 overlay 窗口 | — |
| `recovery.rs` | 核心 | 崩溃恢复：无后端数据库导出 + 目录打开 | — |
| `visual_approval_overlay.rs` | 核心 | 视觉审批红框 overlay | — |
| `session_window.rs` | 核心 | Focused 模式独立会话窗口 | — |

## 依赖

- `runtime` — Sidecar 启停、Appshot force capture
- `agent_runner_rpc` — Agent Runner RPC
- `sessions` / `permissions` / `config` / `utils`
