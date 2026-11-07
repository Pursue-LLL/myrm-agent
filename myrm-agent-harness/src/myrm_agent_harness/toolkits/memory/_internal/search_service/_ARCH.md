# memory/_internal/search_service/

## 架构概述

记忆检索编排：收集、排序、编排与纯函数助手分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出 `MemorySearchService` |
| `base.py` | 实例状态、`FTS5SearcherFunc` 与跨阶段方法声明 |
| `helpers.py` | 时间窗 metadata、告警码、后台任务失败日志与耗时格式化 |
| `collection.py` | 按类型扇出检索、并发收集、失败降级与结果过滤 |
| `ranking.py` | RRF 排序与 raw exchange 裁剪 |
| `orchestrator.py` | 对外 `search()`、deadline 预算、图增强与 trace |
