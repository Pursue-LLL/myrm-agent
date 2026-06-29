# memory 模块架构


---

## 架构概述

App 层记忆模块。提供框架 Protocol 的具体后端实现和记忆运行时绑定装配。

核心记忆能力（Manager、Session、Retriever、Protocols、Types、Strategies）由 PyPI `myrm_agent_harness.toolkits.memory` 提供。
Server 产品层 Shared Context 由 `app/services/memory/shared_context.py` 管理，本模块只消费解析后的 `shared_context_ids`。

---

## 子模块清单

| 模块 | 职责 | 文档 |
|------|------|------|
| `adapters/` | Protocol 适配器（SQLAlchemy, Qdrant, Graph） | [_ARCH.md](adapters/_ARCH.md) |
| `proactive/` | Proactive follow-up（SQLite 生命周期、heartbeat 注入、抽取 hook） | [_ARCH.md](proactive/_ARCH.md) |
| `services/` | 业务逻辑服务（Embedding 适配器） | - |

---

## 根级文件

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 核心 | 模块入口，导出 `create_memory_manager` 和 Embedding 服务 | - |

---

## 框架层对应

| 框架模块 | 路径 |
|------|------|
| 核心能力 | `myrm_agent_harness.toolkits.memory` |
| Agent 工具 | `myrm_agent_harness.agent.tools.memory` |
| 记忆中间件 | `myrm_agent_harness.agent.middlewares.memory_context_middleware` |

---

## 依赖关系

- **内部**：`app/core/retriever/vector/`、`app/core/retriever/graph/`、`app/database/models/`
- **框架**：`myrm_agent_harness.toolkits.memory`（types、protocols、manager）
- **被依赖**：`app/ai_agents/`、`app/api/memory/`
