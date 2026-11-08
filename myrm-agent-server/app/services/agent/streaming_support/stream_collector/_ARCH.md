# streaming_support/stream_collector/

## 架构概述

把 SSE / 事件流转成可持久化回合：`core.py` 持有公开类与事件分发，`handlers.py` 按事件类型收集，`state.py` 只更新内存状态与快照，`constants.py` 定义共享限制与映射。`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `StreamContentCollector` / `ACTIVE_COLLECTORS` / `settle_tool_approvals_of` / `_MAX_REASONING_CHARS` | ✅ |
| `base.py` | 基础 | mixin 共用的实例属性类型声明 | ✅ |
| `constants.py` | 辅助 | SSE 前缀、reasoning 字符上限、failover 步骤映射、中断重放类型 | ✅ |
| `handlers.py` | 核心 | 每个 `_on_<事件类型>` 处理一类事件，并维护 `ACTIVE_COLLECTORS` | ✅ |
| `state.py` | 核心 | 快照、草稿、引用、usage/cost 与 `_sync_run_digest` | ✅ |
| `core.py` | 核心 | `StreamContentCollector` 公开生命周期、`_process_event` 与 `_EVENT_HANDLERS` | ✅ |

## 依赖关系

- `core.py` → `base.py`
- `core.py` → `constants.py`
- `core.py` → `handlers.py`
- `core.py` → `state.py`
- `handlers.py` → `base.py`
- `handlers.py` → `constants.py`
- `handlers.py` → `state.py`
- `state.py` → `base.py`
- `state.py` → `constants.py`
