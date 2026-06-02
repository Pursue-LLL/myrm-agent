# Memory Adapters 架构


---

## 架构概述

Memory 系统的业务层适配器。在最新的 Agent-in-Sandbox 架构下，
业务层不再需要自己实现底层存储适配器（如 SQLAlchemy 或 Qdrant SDK 包装），
而是直接使用 Harness 框架层提供的开箱即用的本地存储引擎（SQLite + Embedded Qdrant）。

`setup.py` 是唯一的组装入口，它通过读取环境变量 `MEMORY_BASE_PATH` 来决定存储路径，
从而实现本地单机运行与云端沙箱挂载卷（`/persistent`）的无缝切换。
同时它会按 binding / approval / embedding / recall 组合缓存 `MemoryManager`，
避免嵌入式 Qdrant 反复抢锁并保证跨请求持久写入。
业务层必须先解析出 `ResolvedMemoryBinding`，再调用本层创建 `MemoryManager`。
`setup.py` 不再接受散装 `agent_id/channel_id/conversation_id/task_id` 作为公共合同，
而是通过统一的 binding 将作用域稳定透传到 Harness。
最新实现中，binding 还会携带 `memory_policy`，由 AgentProfile 作为唯一策略权威来源，
统一控制 recall 可见 scope 与新记忆写入目标，避免业务层在各入口分散拼装策略。
Server 层 Shared Context 会先解析为 `shared_context_ids`，本层只把它们稳定映射为
`shared:<context_id>` namespaces 并附加到 recall 范围；私有写入仍以非 shared namespace 作为 primary。

---

## 文件清单

**要求**：列出本文件夹中**所有**文件的名字、地位、职责。

| 文件/模块 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 📄 占位 | 模块声明 | ❌ |
| `_ARCH.md` | 📄 文档 | 本架构文档 | ❌ |
| `setup.py` | ✅ 核心 | 业务层记忆适配器入口。负责解析/消费 `ResolvedMemoryBinding`，通过环境变量 `MEMORY_BASE_PATH` 动态配置 Harness 的本地存储路径，并将统一 binding、`shared_context_ids` 与 `memory_policy` 稳定透传到 `MemoryManager`；同时按 binding / approval / embedding / recall 组合缓存管理器并在进程关闭时释放缓存。 | ✅ |
| `policy.py` | ✅ 核心 | AgentProfile `memory_policy` 的序列化/反序列化与 binding namespace 派生逻辑；把 Shared Context ID 追加为 `shared:<id>` namespace，确保 Server 侧 runtime contract 与 Harness 侧作用域语义一致。 | ✅ |
| `types.py` | ✅ 核心 | 定义 `ResolvedMemoryBinding`，作为 Server 到 Harness 的唯一记忆运行时合同，包含作用域 ID、namespaces、`shared_context_ids` 和正式的 `memory_policy`。 | ✅ |

---

## 依赖关系

### 内部依赖
- 无

### 外部依赖
- `myrm_agent_harness.toolkits.memory`：提供 `MemoryManager` 和 `create_local_memory_manager`

---

## 文档导航

- [../../../../ARCHITECTURE.md](../../../../ARCHITECTURE.md) - 全局架构文档
