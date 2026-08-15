# Memory Adapters 架构


---

## 架构概述

Memory 系统的业务层适配器。业务层通过 `ResolvedContextBinding` 统一表达记忆作用域与
ContextBundle volume 边界，再调用 `setup.py` 创建 `MemoryManager`。

`setup.py` 读取 `MEMORY_BASE_PATH`（memory scene）决定存储路径，实现 Local 与 SaaS 沙箱卷挂载的无缝切换。
ContextBundle 卷布局由 `myrm_agent_harness.toolkits.context_bundle` 定义（PyPI harness 包）。

---

## 文件清单

| 文件/模块 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 📄 占位 | 模块声明 | ❌ |
| `_ARCH.md` | 📄 文档 | 本架构文档 | ❌ |
| `setup.py` | ✅ 核心 | 解析 `ResolvedContextBinding` 并创建/缓存 `MemoryManager`；`create_memory_tools_for_user` 支持 `description_locale`；`create_conflict_callback` 工厂提供冲突持久化回调（写时按 `importance>=0.9` 分级：high_risk 不设 auto_resolve_at 永不静默保旧，低风险 72h 自动保留旧记忆；持久化成功后异步记录 `MemoryOperationKind.CONFLICT` ledger 事件，经 operation_ledger SSE 推送给前端刷新待裁决角标，失败仅丢通知不影响主流程）；`evict_cached_memory_manager` 联动释放隔离卷的 harness 嵌入式 Qdrant 单例 | ✅ |
| `cascade.py` | ✅ 核心 | Cascade-deletion MemoryManager 单例：按 `source_chat_id` 清理记忆 | ✅ |
| `policy.py` | ✅ 核心 | AgentProfile `memory_policy` 与 namespace 派生 | ✅ |
| `types.py` | ✅ 核心 | `ResolvedContextBinding` — Server 到 Harness 的上下文运行时合同 | ✅ |

---

## 依赖关系

### 外部依赖
- `myrm_agent_harness.toolkits.memory` — `MemoryManager`, `create_local_memory_manager`
- `myrm_agent_harness.toolkits.context_bundle` — bundle spec types (`IncognitoPolicy`, `AgentContextOverlay`)

---

## 文档导航

- [../../../../ARCHITECTURE.md](../../../../ARCHITECTURE.md) — 全局架构
