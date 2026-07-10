# services/wiki 模块架构


## 架构概述

Wiki 知识库服务层：Memory→Wiki 归档、vault 路径 SSOT、启动迁移、compaction 后 SessionNotes 后台归档。

## Vault SSOT

- **Canonical path**: `{harness_dir}/wiki` — `vault_resolver.resolve_wiki_vault_path()`
- **Legacy paths** (one-time migration): `{state_dir}/wiki`, `~/.myrm/users/sandbox/wiki`
- **Startup**: `vault_service.init_wiki_vault_at_startup()` from FastAPI lifespan
- **Shared archiver**: `vault_service.get_wiki_archiver()` — API、SessionNotes 归档钩子与 Deep Research vault 共用

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `memory_to_wiki.py` | 核心 | 记忆转 Wiki；支持 harness SessionNotes 与 legacy JSON | ✅ |
| `vault_resolver.py` | SSOT | 路径解析 + legacy 迁移 | ✅ |
| `vault_service.py` | 生命周期 | 启动迁移、共享 archiver | ✅ |
| `wiki_archive_hook.py` | 钩子 | compaction persist 后 SessionNotes 后台归档 | ✅ |
| `obsidian_adapter.py` | 适配器 | Obsidian Vault 导入预处理 | ✅ |
