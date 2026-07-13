# permissions 模块架构

## 架构概述

CLI 可视化三级权限：Explore（只读）、Ask（默认确认）、Auto（自动批准，危险命令除外）。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | PermissionManager、危险命令黑名单、模式循环 | — |

## 依赖

- `cli_agent_types::PermissionMode`
