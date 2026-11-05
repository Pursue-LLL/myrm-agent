# app/services/agent/params/routing 子包架构

路由子域：本回合跑哪个模型，以及跨回合记住/复用路由结果。路由判定与它读取的历史记忆是同一份审阅对象，因此放在一起。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合导出路由阶段与记忆 API | — |
| `turn_routing.py` | 核心 | specialty 路由（code / long_doc / reasoning）、复杂度路由（`route_task`，judge 取 `lite_model_cfg` 低温 0.0）、重试升档（`complaint_floor()`）、HITL resume 复用被中断回合的模型；决策日志含 `routing_ms`；产出 `RoutingOutcome` | ✅ |
| `routing_memory.py` | 核心 | 跨请求记忆：`load_recent_routing()` 把持久化 `routingTier` 历史按枚举分流为 complexity / specialty 动量；`load_retry_baseline()` + `complaint_floor()` 决定重试下限；`remember_turn_routing()` / `resolve_turn_routing()` 供 resume 复用；进程内 LRU | ✅ |

## 依赖关系

- 上游：`params/conversion/model_plan.py`（槽位）、`params/models.py`
- 下游：harness `toolkits.llms.routing`（引擎）、`app.database.repositories.chat_repo`（档位历史）
- 外部调用方：`app/services/agent/stream_session/orchestrator_turn_setup.py`（记忆写入）、`app/database/repositories/chat_repo.py`（历史读取）
