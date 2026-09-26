# api/skills/discovery/ 子包架构

## 架构概述

技能发现域：搜索、安装、预览、更新、卸载、源管理。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 聚合门面：重导出 `router` 与全部请求/响应模型 | ✅ |
| `discovery.py` | 核心 | Skill discovery API — search/install/enable-after-install/uninstall/sources/registry-probe/pool-sync；search 支持 package_type 过滤与 MCP 声明透传；install/update/uninstall/install-from-url 受沙箱能力门控；uninstall 支持父子技能级联清理、孤儿智能体白名单清理与依赖者校验；/pool/sync 支持跨 Agent 白名单同步与广播 | ✅ |
| `discovery_schemas.py` | 模型 | Discovery request/response Pydantic models（含 package_type, keywords, declared_mcp_servers, installed_skills, SkillPoolSyncRequest, SkillPoolSyncResponse；`SkillUninstallRequest.force` 支持强制卸载依赖者技能） | ✅ |

## 依赖

- `app.core.skills.marketplace` / harness market service — 搜索/安装编排
- `app.api.skills.audit` — 技能动作审计
- `app.api.skills._deploy_capability` — 沙箱落盘门控
