# toolkits/memory/types/

## 架构概述

记忆类型体系：枚举、基础模型、具体记录与检索结果分层，`__init__.py` 是唯一门面并组装 `AnyMemory`。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出全部类型与 `AnyMemory`，执行 `model_rebuild` | ✅ |
| `enums.py` | 核心 | 记忆分类、层级、摘要/蒸发/声明状态、冲突处置、规则优先级 | ✅ |
| `base.py` | 基础 | BaseMemory（含 `stored_at`：存储层写入时盖的到达戳，不同于业务时间 `created_at`）/ MemoryScope / MemoryLifecycle / EvidenceReference / 归档窗口 / 变更 DTO | ✅ |
| `records.py` | 核心 | ProfileEntry 与八类具体记忆模型；语义、情景与程序性记忆用 `source_chat_id`（写入时所在的对话）与 `source_chat_ids`（由多个对话合成时所源自的全部对话）记录来源对话 | ✅ |
| `search.py` | 核心 | 检索来源、白盒追踪、搜索结果与待审候选 | ✅ |

## 依赖关系

- `base.py` → `enums.py`
- `records.py` → `base.py`
- `records.py` → `enums.py`
- `search.py` → `enums.py`
- `search.py` → `records.py`
