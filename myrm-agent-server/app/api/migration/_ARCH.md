# api/migration/

## 架构概述

外部助手数据发现与迁移向导 HTTP 层（三部署均等）。上级文档：[../_ARCH.md](../_ARCH.md)。

- Local/Tauri：`GET /discover` 扫描本地文件系统
- Cloud/SaaS：`POST /upload` 接收用户上传的 ZIP，解压后复用同一套 probe 逻辑

Wizard 支持的 discover 来源封闭为 4 种：Hermes、OpenClaw、Claude Code、Codex。详见 [../../services/migration/_ARCH.md](../../services/migration/_ARCH.md) 支持范围策略。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `discovery.py` | 模块 | `GET /discover` 四源扫描；`POST /secrets/import` opt-in API key 导入 | ✅ |
| `upload.py` | 模块 | `POST /upload` Cloud ZIP 上传迁移桥；解压后调用 `discover_external_sources(home_dir=...)` | ✅ |
