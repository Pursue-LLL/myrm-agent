# graph 模块架构


---

## 架构概述

业务层图存储工厂和 AGE 后端。GraphStore ABC 和 SQLiteGraphStore 位于框架层 `myrm_agent_harness.toolkits.memory.graph`。
本模块提供 AGEStore（PostgreSQL AGE 后端）和工厂函数，根据环境配置选择 SQLite 或 AGE 后端。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `__init__.py` | 核心 | 模块入口，导出 `get_graph_store` |
| `factory.py` | 核心 | 图存储工厂（单例缓存，根据 `DATABASE_URL` 选择后端） |

---

## 依赖关系

**框架层依赖**：
- `myrm_agent_harness.toolkits.memory.graph` — GraphStore ABC + SQLiteGraphStore + 数据模型

**外部依赖**：
- `apache-age-python` — AGE 驱动（仅 AGE 后端，可选）

**被依赖**：
- `app/core/memory/adapters/setup.py` — 记忆系统图存储初始化
