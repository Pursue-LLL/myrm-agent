# retriever 模块架构


---

## 架构概述

统一的检索基础设施，提供向量存储和图存储能力。支持多种存储后端和部署模式，是记忆系统和 Wiki 的底层支撑。

---

## 文件清单

| 文件/目录 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 核心 | 模块入口，公共 API 导出 |
| `vector/` | 核心 | Qdrant 向量数据库封装（嵌入式/远程模式） |
| `graph/` | 核心 | 因果关系图存储（默认 SQLite CTE，可选 AGE） |

---

## 依赖关系

**内部依赖**：
- `qdrant-client` — Qdrant Python SDK
- `sqlalchemy` — ORM 框架（图存储）
- `psycopg2` — PostgreSQL 驱动（仅 AGE 后端，可选）

**被依赖**：
- `app/core/memory/` — 记忆检索
