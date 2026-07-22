# core/integrations/catalog/

## 架构概述

Integration Catalog 预配置服务目录系统。提供 MCP/OpenAPI 服务的预置模板，用户可一键连接而无需手动配置。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块入口 | ✅ |
| `models.py` | 核心 | Pydantic 数据模型（CatalogEntry, MCPPreConfig, AuthRequirements, CredentialField, DeploymentScope 等）；对显式 `local_tauri_only` 条目做 loopback 目标校验 | ✅ |
| `registry.py` | 核心 | CatalogRegistry 单例，懒加载 data/*.json，并将所有 MCP 条目归一化为显式 `deployment_scope`（unreal/blender=`local_tauri_only`，其余=`all_modes`），提供 list/search/get 查询 | ✅ |
| `data/` | 数据 | 按分类组织的 JSON 预配置条目（9 分类 35 条目），详见 [data/_ARCH.md](data/_ARCH.md) | ❌ |

## 依赖关系

- 被 `app/api/integrations/catalog.py` 调用提供 API 端点
- 被前端 IntegrationCatalogSection 通过 `/catalog` API 消费
