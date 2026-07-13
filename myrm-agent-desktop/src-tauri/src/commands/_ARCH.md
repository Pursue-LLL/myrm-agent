# commands 模块架构

## 架构概述

Tauri `invoke` IPC 命令层：薄封装转发到 runtime、sidecar、sessions、utils。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 子模块聚合与 re-export | — |
| `config.rs` | 核心 | 系统配置读写、快捷键、数据目录迁移 | — |
| `agent/mod.rs` | 核心 | CLI Agent 会话与消息 IPC | — |
| `agent/session.rs` | 核心 | 会话 CRUD IPC | — |
| `agent/message.rs` | 核心 | 消息发送/停止 IPC | — |
| `agent/permission.rs` | 核心 | 权限模式 IPC | — |
| `power.rs` | 核心 | 电源锁 IPC（委托 `utils/power`） | — |
| `screen_lock.rs` | 核心 | 锁屏 IPC（委托 `utils/screen_lock`） | — |
| `pet_overlay.rs` | 核心 | 桌面宠物 overlay 窗口 | — |
| `visual_approval_overlay.rs` | 核心 | 视觉审批红框 overlay | — |
| `session_window.rs` | 核心 | Focused 模式独立会话窗口 | — |

## 依赖

- `runtime` — Sidecar 启停、Appshot force capture
- `sidecar` — Agent Runner RPC
- `sessions` / `permissions` / `config` / `utils`
