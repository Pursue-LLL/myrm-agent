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
| `setup.py` | ✅ 核心 | 解析 `ResolvedContextBinding` 并创建/缓存 `MemoryManager`；`create_conflict_callback` 工厂提供冲突持久化回调 | ✅ |
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
