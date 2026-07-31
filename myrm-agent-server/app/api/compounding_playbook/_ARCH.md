# api/compounding_playbook/ 模块架构

## 架构概述

MSC 复利闭环轻量状态 HTTP 层。只返回四行 checklist 计数，不构建 Memory Command Center 全量快照。
业务聚合在 [app/services/compounding_playbook/_ARCH.md](../../services/compounding_playbook/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | Compounding playbook API exports | ✅ |
| `router.py` | 路由 | `GET /compounding-playbook/status?agent_id=` | ✅ |

## 模块依赖

- `app.services.compounding_playbook.status_service` — 四行 checklist 计数
- `app.services.memory.manager_deps` — MemoryManager 注入
- `app.api.cron.routes.helpers` — CronManager 注入
