# api/migration/

## 架构概述

竞品数据发现与迁移向导 HTTP 层（仅 local/Tauri）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `discovery.py` | 模块 | Local/Tauri-only endpoint for competitor data auto-discovery. | ✅ |
