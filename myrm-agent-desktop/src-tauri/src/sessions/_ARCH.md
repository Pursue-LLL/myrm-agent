# sessions 模块架构

## 架构概述

CLI Agent 会话生命周期：内存存储 + 可选 JSONL 持久化，状态机转换校验。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 聚合 | 模块导出 | — |
| `types.rs` | 核心 | `Session` 结构与状态转换 | — |
| `manager.rs` | 核心 | `SessionManager` 存储与持久化 | — |

## 依赖

- `cli_agent_types::{PermissionMode, SessionStatus}`
