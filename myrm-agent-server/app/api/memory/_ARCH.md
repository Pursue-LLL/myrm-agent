# api/memory/

## 架构概述

记忆 CRUD 与导入入口 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Memory API module | ✅ |
| `router.py` | 路由 | Memory API 聚合路由。产线冲突 SSOT：`operations/conflicts` + `operations/pending`（consolidation → `conflict_callback` → PendingMemory）。`/memory/command-center*` 仅在 `MYRM_MEMORY_LABS=1` 时挂载；Chrome E2E seed 路由仅在 `is_local_mode()` 时挂载。所有 API 路由都必须有前端调用或登记的外部消费者，由 `tests/architecture/test_api_route_consumers.py` 守卫；新增路由先接前端或登记，不预埋无调用方的实验路由；无条件挂载的子路由另由 `tests/architecture/test_memory_router_mounts.py` 登记在册，新增须收进 `MYRM_MEMORY_LABS` 开关或写明默认可见调用方 | ✅ |
| `test_seed.py` | 路由 | 本地测试专用 fixture（仅 local mode）：Chrome E2E seed 演变历史/纠正链记忆（预填向量绕过失效凭据）；`/test/seed-pending-proposal` 经 `submit_pending` 排队 CORRECT/DELETE 待审批提案（manager 跟随已存储的检索配置，未配 embedding 时为关键词模式） | ✅ |
| `follow_ups/` | 路由 | Proactive follow-up list / dismiss / snooze | [_ARCH.md](follow_ups/_ARCH.md) |
| `shared_context_schemas.py` | 模块 | 共享上下文 API Schema 层。集中定义 Shared Context 产品接口的数据契约。 | ✅ |
| `utils.py` | 模块 | Memory API utilities — re-exports shared service-layer helpers for route modules. | ✅ |
| `recall_simulator_router.py` | 路由 | Item 68 记忆与经验基因交互式召回模拟沙盒与二次治理路由（`/simulate-recall`；演示数据引擎、无持久化，只在 `MYRM_MEMORY_LABS` 开启时挂载） | ✅ |

