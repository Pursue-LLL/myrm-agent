# api/skills/

## 架构概述

技能 HTTP 层：CRUD、批量导入、权限、经验账本与增长投影。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Skills management API module | ✅ |
| `_deploy_capability.py` | 模块 | 部署能力门控：`require_local_skills_capability()` 供所有落盘本地技能的 install/import/export API 复用，沙箱模式 fail-closed。 | ✅ |
| `_staging.py` | 模块 | 管理批量导入技能时的持久化暂存区 (Persistent Staging Area)。 | ✅ |
| `audit.py` | 模块 | Structured audit log for skill lifecycle operations. | ✅ |
| `batch_import.py` | 模块 | 批量导入 (GUI-First 技能迁移) 接口；`preview/confirm` 错误统一输出 `detail={message,error_code}`，归档安全错误映射为用户安全文案；本地落盘入口受沙箱能力门控。 | ✅ |
| `config.py` | 模块 | User skill config CRUD；GET 返回 registry_presets + clawhub_registry_url | ✅ |
| `config_version.py` | 模块 | Re-export from app.core.skills.config_version（单一来源）。 | ✅ |
| `core.py` | 模块 | 核心技能获取与 reveal；list/get 时 apply integration OAuth availability | ✅ |
| `curator.py` | 模块 | Curator API — skill lifecycle management endpoints. | ✅ |
| `discovery.py` | 模块 | Skill discovery API — search/install/enable-after-install/uninstall/sources/registry-probe；install/update/uninstall/install-from-url 受沙箱能力门控 | ✅ |
| `discovery_schemas.py` | 模块 | Discovery request/response Pydantic models（含 install enable + allowlist_appended/allowlist_append_error） | ✅ |
| `drafts.py` | 模块 | Agent Draft Inbox API：按 status 查询 growth drafts；`POST /drafts/test/seed-mock?agent_id=` 本地 E2E seed；approve skill_draft/skill_patch 受沙箱能力门控（延迟导入避免 router 循环依赖） | ✅ |
| `experience_ledger.py` | 模块 | 经验账本接口层。对外暴露原始 ledger 事件查询，以及 skill-growth projection 事件/摘要查询。 | ✅ |
| `growth.py` | 模块 | Unified skill growth API：`GET /cases` summary、`GET /cases/{id}` detail、`GET /stats` 全量 status COUNT 统计 | ✅ |
| `instances.py` | 模块 | Skill instances API - CRUD operations for multi-instance skill support. | ✅ |
| `local.py` | 模块 | Local skills management endpoints | ✅ |
| `migrations.py` | 模块 | Controlled migration review API；approve skill_import 直接写 `~/.myrm/skills`，受沙箱能力门控（延迟导入避免独立加载循环依赖） | ✅ |
| `packaging.py` | 模块 | Skill packaging and upload endpoints | ✅ |
| `permissions.py` | 模块 | Skill Permission Management API | ✅ |
| `prebuilt.py` | 模块 | Prebuilt skill admin and update management API. | ✅ |
| `quality.py` | 模块 | Skill Quality Aggregation API | ✅ |
| `router.py` | 路由 | Skills API router — aggregates all skill-related endpoints. | ✅ |
| `schemas.py` | 模块 | Skills API request/response schemas. | ✅ |
| `sync.py` | 模块 | Skill synchronization and backup protocol；import 受沙箱能力门控（export 只读天然安全） | ✅ |
| `ws_evolution.py` | 模块 | WebSocket Evolution Proposal Streaming — HTTP transport only. | ✅ |
