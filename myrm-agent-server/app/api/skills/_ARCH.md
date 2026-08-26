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
| `batch_import/`（子包） | 模块 | 批量导入 (GUI-First 技能迁移) 域：`batch_import.py`（`preview/confirm` 路由，错误统一输出 `detail={message,error_code}`）、`batch_import_execute.py`（落盘执行器 `execute_batch_import_confirm`，蓝绿原子写入 + DB 事务）、`batch_import_helpers.py`（错误映射助手）、`batch_import_schemas.py`（请求/响应 Pydantic 模型）。`batch_import/__init__.py` 为聚合门面（导出 `router`）。 | ✅ |
| `config.py` | 模块 | User skill config CRUD；GET 返回 registry_presets + clawhub_registry_url；`POST /{skill_id}/disable` 支持依赖者校验（存在依赖者且非 force 时返回 409 DEPENDENTS_EXIST + impacted_dependents） | ✅ |
| `config_version.py` | 模块 | Re-export from app.core.skills.config_version（单一来源）。 | ✅ |
| `core.py` | 模块 | 核心技能获取与 reveal；list/get 时 apply integration OAuth availability | ✅ |
| `curator.py` | 模块 | Curator API — skill lifecycle management endpoints. | ✅ |
| `desktop_recorder.py` | 模块 | Desktop Workflow Skill Recorder API — 桌面操作录制会话、事件流收集、意图与Tool Lifting技能合成及落盘发布。 | ✅ |
| `discovery.py` | 模块 | Skill discovery API — search/install/enable-after-install/uninstall/sources/registry-probe/pool-sync；search 支持 package_type 过滤与 MCP 声明透传；install/update/uninstall/install-from-url 受沙箱能力门控；uninstall 支持父子技能级联清理、孤儿智能体白名单清理与依赖者校验；/pool/sync 支持跨 Agent 白名单同步与广播 | ✅ |
| `discovery_schemas.py` | 模块 | Discovery request/response Pydantic models（含 package_type, keywords, declared_mcp_servers, installed_skills, SkillPoolSyncRequest, SkillPoolSyncResponse；`SkillUninstallRequest.force` 支持强制卸载依赖者技能） | ✅ |
| `drafts.py` | 模块 | Agent Draft Inbox API：按 status 查询 growth drafts；`POST /drafts/test/seed-mock?agent_id=` 本地 E2E seed；approve skill_draft/skill_patch 受沙箱能力门控（延迟导入避免 router 循环依赖） | ✅ |
| `experience_ledger.py` | 模块 | 经验账本接口层。对外暴露原始 ledger 事件查询，以及 skill-growth projection 事件/摘要查询。 | ✅ |
| `growth.py` | 模块 | Unified skill growth API：`GET /cases` summary、`GET /cases/{id}` detail、`GET /stats` 全量 status COUNT 统计；summary/detail 均携带 `impacted_dependents`（依赖本技能的库内技能 ID，经 core/skills/dependency_guard 查询） | ✅ |
| `instances.py` | 模块 | Skill instances API - CRUD operations for multi-instance skill support. | ✅ |
| `local.py` | 模块 | Local skills management endpoints | ✅ |
| `migrations.py` | 模块 | Controlled migration review API；approve skill_import 直接写 `~/.myrm/skills`，受沙箱能力门控（延迟导入避免独立加载循环依赖） | ✅ |
| `packaging.py` | 模块 | Skill packaging and upload endpoints | ✅ |
| `permissions.py` | 模块 | Skill Permission Management API | ✅ |
| `prebuilt.py` | 模块 | Prebuilt skill admin and update management API. | ✅ |
| `quality.py` | 模块 | Skill Quality Aggregation API | ✅ |
| `rescan.py` | 模块 | Skill supply chain rescan and advisory acknowledgment API (`POST /rescan`, `GET /rescan/report`, `POST /advisories/ack`, `POST /advisories/unack`, `GET /advisories/acks`). | ✅ |
| `rescan_schemas.py` | 模块 | Request/response Pydantic schemas for rescan and advisory governance endpoints. | ✅ |
| `router.py` | 路由 | Skills API router — aggregates all skill-related endpoints. | ✅ |
| `schemas.py` | 模块 | Skills API request/response schemas. | ✅ |
| `sync.py` | 模块 | Skill synchronization and backup protocol；export 打包 `manifest.json`（format/format_version/skills[].sha256+version），import 按 manifest 做完整性校验并返回 `imported/updated/unchanged/hash_mismatch` 恢复摘要；`_safe_extract` 逐成员校验路径（绝对路径/`..` 穿越/反斜杠分隔符归一化），恶意 ZIP 返回 400；import 受沙箱能力门控（export 只读天然安全） | ✅ |
| `ws_evolution.py` | 模块 | WebSocket Evolution Proposal Streaming — HTTP transport only. | ✅ |
