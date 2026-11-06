# app/database/repositories/agent_repo 子包架构

Agent 领域仓储。类不持有实例状态：8 个方法全部是 `@staticmethod`，`db: AsyncSession` 由调用方传入；按读写与映射拆成 4 个 mixin。`app.database.repositories.agent_repo` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 导出 `AgentRepository` | — |
| `store.py` | 核心 | `AgentRepository(ReadsMixin, CreateMixin, UpdateMixin, MappingMixin)`，无 `__init__`、无实例状态 | — |
| `mapping.py` | 辅助 | `_agent_to_profile`（ORM ↔ `AgentProfile`）、`_prepare_engine_params` 投影 | — |
| `reads.py` | 核心 | `get_profile` / `list_profiles`（分页）/ `count_profiles` | ✅ |
| `create.py` | 核心 | `create_profile` / `delete_profile` | ✅ |
| `update.py` | 核心 | `update_profile`（含乐观并发 `StaleDataError` 处理） | ✅ |

## 说明

- mutation 后 `flush` + `refresh` 再映射的行为原样保留在 `create.py` / `update.py`，避免 async lazy-load `updated_at`。
- 内部映射调用由 `AgentRepository._agent_to_profile(...)` 改为 `MappingMixin._agent_to_profile(...)`（同一 staticmethod，语义不变）。

## 依赖关系

- 上游：`app.database.models`、`app.ai_agents.personality_templates`、harness `backends.profiles.types` / `toolkits.memory.config`
- 下游：`app/database/repositories/uow.py`、`app/api/agents/**`、`app/services/agent/**`
