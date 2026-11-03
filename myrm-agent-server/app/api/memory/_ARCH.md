# api/memory/

## 架构概述

记忆 CRUD 与导入入口 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Memory API module | ✅ |
| `router.py` | 路由 | Memory API 聚合路由。产线冲突 SSOT：`operations/conflicts` + `operations/pending`（consolidation → `conflict_callback` → PendingMemory）。`/memory/command-center*`、归档恢复（`/archive/restore`）、工具指引（`/tool-guidance`）、画像笔记（`/profile-notes`）、首次见面（`/onboarding`）、临时增量（`/ephemeral-delta`）、认知时钟状态与 T1 触发（`/guardian/cognitive-clock/status`、`/guardian/cognitive-clock/trigger-t1`）、导入回滚预演（`/import/rollback/dry-run`）与 6 组引擎控制台（`/budget-packing`、`/cubes`、`/score-honesty`、`/notebook`、`/chunker`、`/two-layer-dialectic`）仅在 `MYRM_MEMORY_LABS=1` 时挂载，`/command-center*` 的唯一例外是 `/command-center/graph`（成长页知识图谱标签页）与 `/command-center/evidence/playback`（记忆卡片证据抽屉），它们由 `operations/memory_graph.py`、`operations/evidence_playback.py` 对所有用户挂载；Chrome E2E seed 路由仅在 `is_local_mode()` 时挂载。所有 API 路由都必须有前端调用或登记的外部消费者，由 `tests/architecture/test_api_route_consumers.py` 守卫；新增路由先接前端或登记，不预埋无调用方的实验路由；无条件挂载的子路由另由 `tests/architecture/test_memory_router_mounts.py` 登记在册，新增须收进 `MYRM_MEMORY_LABS` 开关或写明默认可见调用方 | ✅ |
| `budget_packing_router.py` | 路由 | 预算召回装箱 API（`/budget-packing`）：`POST /pack` 在 token 预算内按边际效用密度挑选候选记忆，`GET /default-budget` 返回平台默认预算与多样性惩罚参数；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `ephemeral_delta_router.py` | 路由 | 临时增量记忆 API（`/ephemeral-delta`）：`POST /record` 记录不使提示缓存失效的临时纠正或推断事实，`GET /active/{session_id}`、`/snapshot/{session_id}`、`/metrics/{session_id}` 读取会话内的活跃增量、缓冲快照与布局诊断，`POST /preview` 预演冻结前缀与尾部增量注入；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `markdown_chunker.py` | 路由 | Markdown 滑动窗口分块 API（`/chunker`）：`POST /slice` 切片并带行号指针，`/incremental-index` 只索引相对缓存有变化的内容，`/hydrate` 按行号指针展开上下文；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `mem_cube_router.py` | 路由 | Memory Cube 作用域隔离与动态挂载 API（`/cubes`）：创建、列出、读取、删除 cube，按 agent 设置与读取读写挂载策略，经挂载策略写入与跨 cube 聚合查询，查看矩阵总览与 cube 近期记录；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `migration_readiness_seed.py` | 路由 | 迁移就绪度 Chrome E2E 种子路由（仅 local mode 挂载，不进 OpenAPI）：`POST /test/seed-migration-readiness-fixture` 写入导入后的就绪度批次 | ✅ |
| `onboarding.py` | 路由 | 外部 Agent 历史接入与初见报告 API（`/onboarding`）：`/scan-sources` 探测宿主机上的 Agent 来源，`/generate-report` 采样历史会话生成初见画像，`/confirm-ingest` 把用户确认的条目写入目标 Agent 或全局记忆；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `private_notebook_router.py` | 路由 | 模型私有笔记本 API（`/notebook`）：笔记的列表、搜索、读取、追加、改写与删除，历史上下文列表与历史检索，`POST /new-context` 在保留笔记与沙箱状态的前提下切换到干净的上下文窗口；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `profile_notes_router.py` | 路由 | 用户画像与工作笔记预算守卫 API（`/profile-notes`）：`POST /intake-check` 按临时噪声过滤规则评估候选文本，`GET/PUT /contents` 读取与更新 USER、MEMORY 两层内容并校验容量预算；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `score_honesty_router.py` | 路由 | 检索分数诚实度 API（`/score-honesty`）：`POST /evaluate` 对候选记忆做双阈值评估并给出完整归因，`POST /filter` 返回放行列表，`GET /stats` 返回最近的诊断统计，`GET /health` 为存活探针；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `two_layer_dialectic_router.py` | 路由 | 两层上下文注入与多轮辩证调和 API（`/two-layer-dialectic`）：`/inspect` 检出相互对立的陈述，`/reconcile` 执行审视、综合与调和，`/assemble` 组装第一层（缓存安全的基础上下文）与第二层（尾部调和块），`GET /cache/{session_id}` 读取缓存的基础上下文，`POST /reset/{session_id}` 清除会话的节奏计数与缓存；只有 Memory Labs 面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `test_seed.py` | 路由 | 本地测试专用 fixture（仅 local mode）：Chrome E2E seed 演变历史/纠正链记忆（预填向量绕过失效凭据）；`/test/seed-pending-proposal` 经 `submit_pending` 排队 CORRECT/DELETE 待审批提案（manager 跟随已存储的检索配置，未配 embedding 时为关键词模式） | ✅ |
| `follow_ups/` | 路由 | Proactive follow-up list / dismiss / snooze | [_ARCH.md](follow_ups/_ARCH.md) |
| `shared_context_schemas.py` | 模块 | 共享上下文 API Schema 层。集中定义 Shared Context 产品接口的数据契约。 | ✅ |
| `utils.py` | 模块 | Memory API utilities — re-exports shared service-layer helpers for route modules. | ✅ |

