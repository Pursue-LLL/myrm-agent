# api/migration/

## 架构概述

外部助手数据发现与迁移向导 HTTP 层（三部署均等）。上级文档：[../_ARCH.md](../_ARCH.md)。

- Local/Tauri：`GET /discover` 扫描本地文件系统
- Cloud/SaaS：`POST /upload` 接收用户上传的 ZIP，解压后复用同一套 probe 逻辑
- 两个入口统一返回 `source_manifest` + `source_manifest_authoritative`（server 下发迁移来源元数据 SSOT 及覆盖语义；当 payload 未完整覆盖 SSOT ids 时自动降级 authoritative=false）

Wizard 自动发现的本机来源封闭为 6 种：Hermes、OpenClaw、Claude Code、Codex、Pi、PLUR；ChatGPT 与 gbrain 只经 ZIP 上传，PLUR 两种方式都支持。详见 [../../services/migration/_ARCH.md](../../services/migration/_ARCH.md) 支持范围策略。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `discovery.py` | 模块 | `GET /discover` 六源扫描（`can_import_secrets` 告诉向导是否提供密钥导入勾选）；`POST /secrets/import` opt-in API key 导入（仅本机/Tauri，响应列出已导入与未导入的变量名及原因） | ✅ |
| `upload.py` | 模块 | `POST /upload` Cloud ZIP 上传迁移桥；解压前校验压缩包体积、成员数、路径安全与解压后总体积/单文件上限（防 zip bomb），顺带清扫过期的 `myrm_migration_*` 目录，解压后调用 `discover_external_sources(home_dir=...)` | ✅ |
