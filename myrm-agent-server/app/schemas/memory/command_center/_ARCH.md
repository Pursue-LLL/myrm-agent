# app/schemas/memory/command_center 子包架构

记忆指挥中心的 HTTP 响应契约。按响应族分模块，`__init__.py` 聚合全部模型（`from app.schemas.memory.command_center import X` 保持不变）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 52 个模型 + `MemoryCommandMigrationImportSource` 别名 | — |
| `overview.py` | 核心 | 概览、命令空间、治理项、健康、时间线、平面摘要、运行时状态与顶层 `MemoryCommandCenterResponse` | ✅ |
| `economics.py` | 核心 | 影响归因、成本画像、单轮经济性与寄生记忆 | ✅ |
| `replay.py` | 核心 | 冲突重放、trace run 与单轮瀑布 | ✅ |
| `diagnostics.py` | 核心 | 医生检查、探针结果、SLO、基准摘要与修复计划 | ✅ |
| `migration.py` | 辅助 | 迁移来源清单与 provenance（含 `ImportSource` 别名） | ✅ |
| `graph.py` | 核心 | 记忆图节点、边、枢纽与图响应 | ✅ |
| `actions.py` | 核心 | 指挥中心动作与修复动作的请求/响应体 | ✅ |
| `recall.py` | 核心 | recall 作用域边界、四分区摘要、候选/已批准记录与行为洞察 | ✅ |
| `evidence.py` | 核心 | 证据回放与 repo 证据响应 | ✅ |

## 依赖关系

- 上游：`pydantic`、`app.schemas.memory.import_sources`（`ImportSource`）、harness `MemoryRepairExecutionResult`
- 下游：`app/api/memory/*` 路由、`app/services/memory/command_center/*`
