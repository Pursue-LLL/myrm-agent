# zero_replay/

## 架构概述

基于单次原子状态快照与零事件重放 Live SSE 订阅的前后端无缝重连协议服务端业务层（Item 36 P0）。
直击长任务弱网重连与客户端状态同步核心痛点，彻底解决重连回放历史事件导致的 UI 闪烁与事件乱序。
上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出门面 `ZeroReplaySnapshotService` | ✅ |
| `service.py` | 核心 | `ZeroReplaySnapshotService` 单例服务，管理会话原子快照编译、epoch 判定、版本单调自增与 Live 增量过滤 | ✅ |

## 依赖

- `myrm_agent_harness.agent.streaming.zero_replay` — Harness 框架层零重放引擎与快照契约
