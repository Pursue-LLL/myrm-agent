# api/skills/rescan/

## 架构概述

技能供应链重扫与公告治理接口域：触发重扫、查询报告、公告 ack/unack。声明与 schema 收敛于本子包，对外由 `__init__.py` 门面聚合。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 `router` 与全部 schema 名，保持外部 import 稳定 | ✅ |
| `rescan.py` | 核心 | `/rescan`、`/rescan/report`、`/advisories/ack`、`/advisories/unack`、`/advisories/acks` 路由 | ✅ |
| `rescan_schemas.py` | 契约 | 请求/响应 Pydantic 模型（`RescanTriggerRequest`、`RescanReportResponse`、`SkillRescanItemResponse`、`AdvisoryAck*`、`AdvisoryUnackRequest`） | ✅ |

## 依赖

- `app.core.skills.discovery.rescan_service::rescan_service` — 重扫引擎
- `app.api.skills._deploy_capability` — 沙箱能力门控
