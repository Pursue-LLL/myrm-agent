# api/migration/

## 架构概述

外部助手数据发现与迁移向导 HTTP 层（仅 local/Tauri）。上级文档：[../_ARCH.md](../_ARCH.md)。

Wizard 支持的 discover 来源封闭为 4 种：Hermes、OpenClaw、Claude Code、Codex。详见 [../../services/migration/_ARCH.md](../../services/migration/_ARCH.md) 支持范围策略。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `discovery.py` | 模块 | Local/Tauri-only endpoint for external assistant data auto-discovery. | ✅ |
