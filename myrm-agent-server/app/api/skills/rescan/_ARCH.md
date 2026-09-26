# api/skills/rescan/ 子包架构

## 架构概述

技能供应链重扫与公告治理域。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 聚合门面：重导出 `router` 与全部请求/响应模型 | ✅ |
| `rescan.py` | 核心 | Supply chain rescan 与 advisory 治理端点：触发重扫、查看漏洞公告、管理手工公告确认 | ✅ |
| `rescan_schemas.py` | 模型 | Rescan/advisory request/response Pydantic models | ✅ |

## 依赖

- `app.core.skills.discovery.rescan_service` — 重扫引擎
- `app.api.skills._deploy_capability` — 沙箱落盘门控
