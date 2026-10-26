# Memory Adapters 架构


---

## 架构概述

Memory 系统的业务层适配器。业务层通过 `ResolvedContextBinding` 统一表达记忆作用域与
ContextBundle volume 边界，再调用 `setup.py` 创建 `MemoryManager`。

`setup.py` 读取 `MEMORY_BASE_PATH`（memory scene）决定存储路径，实现 Local 与 SaaS 沙箱卷挂载的无缝切换。
ContextBundle 卷布局由 `myrm_agent_harness.toolkits.context_bundle` 定义（同仓 `myrm-agent-harness/`）。

---

## 文件清单

| 文件/模块 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 📄 占位 | 模块声明 | ❌ |
| `_ARCH.md` | 📄 文档 | 本架构文档 | ❌ |
| `setup.py` | ✅ 核心 | 解析 `ResolvedContextBinding` 并创建/缓存 `MemoryManager`；装配 `create_conflict_callback`；`evict_cached_memory_manager` 联动释放隔离卷的 harness 嵌入式 Qdrant 单例 | ✅ |
| `conflict_callback.py` | ✅ 核心 | `get_memory_conflict_policy`（GUI 文案 SSOT：`low_risk_auto_resolve_hours`）；`create_conflict_callback` 将 consolidation 矛盾写入 PendingMemory（importance≥0.9 不设 auto_resolve_at；低风险 72h deadline；同源 old_memory_id 去重；ledger SSE 非致命） | ✅ |
| `cascade.py` | ✅ 核心 | Cascade-deletion MemoryManager 单例：支持按 `source_chat_id` 与 `project_id`（`purge_project_memories` 专属命名空间双重级联清理）销毁记忆数据；删除跨所有 embedding 模型的集合族，故其 `embedding_model` 为固定占位 | ✅ |
| `policy.py` | ✅ 核心 | AgentProfile `memory_policy` 与 namespace 派生：策略分支保留调用方显式 namespace（`ident:<id>`）与共享上下文；`compartment_memory_policy()` 把渠道群聊 / 访客 / 配对成员 turn 收窄为「仅会话 + 显式 compartment」读域、`INHERIT` 写链、关闭 L3 抽取，owner 的 `global` / `agent:<id>` 不在这些 turn 的绑定内 | ✅ |
| `types.py` | ✅ 核心 | `ResolvedContextBinding` — Server 到 Harness 的上下文运行时合同 | ✅ |

---

## 依赖关系

### 外部依赖
- `myrm_agent_harness.toolkits.memory` — `MemoryManager`, `create_local_memory_manager`
- `myrm_agent_harness.toolkits.context_bundle` — bundle identity constants (`DEFAULT_BUNDLE_ID`, schema/layout versions) and `ContextBundleFacade`

---

## 文档导航

- [../../../../ARCHITECTURE.md](../../../../ARCHITECTURE.md) — 全局架构
