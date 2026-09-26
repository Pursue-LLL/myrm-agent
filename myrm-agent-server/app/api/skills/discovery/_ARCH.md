# api/skills/discovery/

## 架构概述

技能发现接口域：搜索、安装/预览、更新检查、卸载、镜像探针、URL 分析与自定义来源管理。声明与 schema 收敛于本子包，对外由 `__init__.py` 门面聚合。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 `router` 与全部 schema 名，保持外部 import 稳定 | ✅ |
| `discovery.py` | 核心 | `/discovery/*` 路由：search（含 package_type 过滤与 MCP 声明透传）、install/update/uninstall（受沙箱能力门控）、preview、registry-probe、analyze-url、custom sources、`/pool/sync`；uninstall 支持父子技能级联清理与依赖者校验 | ✅ |
| `discovery_schemas.py` | 契约 | 请求/响应 Pydantic 模型（含 `SkillInstallRequest`、`SkillPreviewResponse`、`CustomSource*`、`SkillPoolSync*`、`StaticIndexStatusResponse`） | ✅ |

## 依赖

- `app.api.skills._deploy_capability` — 落盘本地技能的沙箱能力门控
- `app.api.skills.audit::_audit_skill_action` — 技能操作审计
- `myrm_agent_harness.toolkits...market` / `app.core.skills.marketplace` — 搜索与安装编排
