# services/memory/conclusion_evidence 模块架构

## 架构概述

结论证据的业务服务适配层：持有单例 harness `ConclusionEvidenceSuite`，提供创建结论、前提/衍生追溯、双向遍历、带证据的对话与统计查询，并把 harness 结果转换为 API DTO。执行逻辑全部在 harness。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 包标记 | — |
| `provider.py` | 核心 | suite 单例（`get_conclusion_evidence_suite` / `reset_conclusion_evidence_suite`）、`execute_create_conclusion`、`query_conclusion` / `query_premises` / `query_derivatives` / `query_two_way_traversal`、`execute_chat_with_evidence`、`get_evidence_stats` | ✅ |

## 模块依赖

- 上游：`myrm_agent_harness.toolkits.memory`（`ConclusionEvidenceSuite` 等）、`app.schemas.conclusion_evidence`（DTO）
- 下游：`app/api/memory/conclusion_evidence_router.py`
