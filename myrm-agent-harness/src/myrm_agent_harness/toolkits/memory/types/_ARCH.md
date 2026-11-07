# toolkits/memory/types/

## 架构概述

记忆类型体系：枚举、基础模型、具体记录与检索结果分层，`__init__.py` 是唯一门面并组装 `AnyMemory`。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出全部类型与 `AnyMemory`，执行 `model_rebuild` |
| `enums.py` | 记忆分类、层级、摘要/蒸发/声明状态、冲突处置、规则优先级 |
| `base.py` | BaseMemory（含 `stored_at`：存储层写入时盖的到达戳，不同于业务时间 `created_at`）/ MemoryScope / MemoryLifecycle / EvidenceReference / 归档窗口 / 变更 DTO |
| `records.py` | ProfileEntry 与八类具体记忆模型 |
| `search.py` | 检索来源、白盒追踪、搜索结果与待审候选 |
