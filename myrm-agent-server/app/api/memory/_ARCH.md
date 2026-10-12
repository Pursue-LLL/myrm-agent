# api/memory/

## 架构概述

记忆 CRUD 与导入入口 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Memory API module | ✅ |
| `router.py` | 路由 | Memory API router（含 `/follow-ups` 子路由、`/archive/restore` 归档恢复路由组） | ✅ |
| `test_seed.py` | 路由 | 本地测试专用 fixture（仅 local mode）：Chrome E2E seed 演变历史/纠正链记忆（预填向量绕过失效凭据）；`/test/seed-pending-proposal` 经 `submit_pending` 排队 CORRECT/DELETE 待审批提案（embedding 由调用方配置） | ✅ |
| `follow_ups/` | 路由 | Proactive follow-up list / dismiss / snooze | [_ARCH.md](follow_ups/_ARCH.md) |
| `shared_context_schemas.py` | 模块 | 共享上下文 API Schema 层。集中定义 Shared Context 产品接口的数据契约。 | ✅ |
| `utils.py` | 模块 | Memory API utilities — re-exports shared service-layer helpers for route modules. | ✅ |
| `snapshot_freshness_router.py` | 路由 | Item 157 快照滞后感知记忆新鲜度与查盘指示路由（`/snapshot-freshness`） | ✅ |
| `staleness_consolidation_router.py` | 路由 | Item 158 自动记忆陈旧衰减探测与盘点重塑路由（`/staleness-consolidation`） | ✅ |


