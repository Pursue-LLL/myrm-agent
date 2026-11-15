# streaming_support/stream_collector/

## 架构概述

把 SSE / 事件流转成可持久化回合：`core.py` 持有公开类与事件分发，`handlers.py` 按事件类型收集，`state.py` 只更新内存状态与快照，`constants.py` 定义共享限制与映射。`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `StreamContentCollector` / `ACTIVE_COLLECTORS` / `settle_tool_approvals_of` / `release_parked_hitl` / `_MAX_REASONING_CHARS` | ✅ |
| `base.py` | 基础 | mixin 共用的实例属性类型声明 | ✅ |
| `constants.py` | 辅助 | SSE 前缀、reasoning 字符上限、failover 步骤映射、中断重放类型 | ✅ |
| `handlers.py` | 核心 | 每个 `_on_<事件类型>` 处理一类事件，并维护 `ACTIVE_COLLECTORS` | ✅ |
| `state.py` | 核心 | 快照、草稿、引用、usage/cost 与 `_sync_run_digest` | ✅ |
| `core.py` | 核心 | `StreamContentCollector` 公开生命周期、`_process_event` 与 `_EVENT_HANDLERS`；`ACTIVE_COLLECTORS`（每个聊天停着的那一轮）及对它的两个动作：`settle_tool_approvals_of`（答复被受理：只摘掉已答的工具审批卡，卡后的续跑接手登记）、`release_parked_hitl`（对话翻篇：聊天被删除、清空、改写，或收到一条不是答复的新消息；该聊天停着的收集器仍握着待重放的中断时，认领 `ApprovalTimeoutScheduler` 的仲裁键并丢弃该收集器，使旧卡的计时器不再续跑、迟到的答复与「跳过」得 409；没有停着的卡时什么也不做，不认领仲裁键） | ✅ |

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
