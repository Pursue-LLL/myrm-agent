# services/memory/conclusion_attribution 模块架构

## 架构概述

结论归因的业务服务适配层：包装 harness `ConclusionAttributionSuite`，把领域实体（结论、图遍历节点、对话证据、涟漪影响报告、归因指标）转换为 API DTO，并维护单进程内的 suite 状态。执行逻辑全部在 harness，本目录只做 DTO 转换与状态持有。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `provider.py` | 核心 | `ConclusionAttributionProvider`：持有 harness suite、`_to_dto` / `_to_node_dto` / `_to_evidence_dto` 领域→DTO 转换 | — |

## 模块依赖

- 上游：`myrm_agent_harness.toolkits.memory.conclusion_attribution`（执行引擎）、`app.schemas.conclusion_attribution`（DTO）
- 下游：`app/api/memory/conclusion_attribution_router.py`
