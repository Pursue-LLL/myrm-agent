# search_catalog/

## 架构概述

搜索服务商 Manifest SSOT。Settings UI 与 config 解析共用同一份 `manifest.json`，避免前后端 provider 列表漂移。

上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manifest.json` | 数据 | Provider slug、connector、deployment_scope、requiresApiKey、backendReady（`volcengine_doubao` → `true` since web MVP） | — |
| `models.py` | 模型 | `SearchProviderManifestEntry` Pydantic 模型 | ✅ |
| `registry.py` | 注册表 | 加载 manifest、按 deploy mode 过滤、max chain size | ✅ |
| `migration.py` | 迁移 | legacy `role` primary/fallback → `priority` 整数 | ✅ |
| `__init__.py` | 入口 | 导出 registry 与 models | ✅ |

## 模块依赖

- `app/api/integrations/search.py` — `GET /providers`、`POST /verify`
- `app/core/channel_bridge/config_parsers.py` — `extract_search_provider_chain`
- `app/api/config/router.py` — Omni-Config save 前 normalize
