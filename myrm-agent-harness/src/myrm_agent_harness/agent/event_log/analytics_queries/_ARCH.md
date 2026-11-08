# agent/event_log/analytics_queries/

## 架构概述

EventLogger 的读侧查询按分析域分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出全部查询函数 | ✅ |
| `common.py` | 辅助 | 事件收集、时长与失败原因提取 | ✅ |
| `tool_usage.py` | 核心 | 工具使用统计、全局稳定性、单 Agent 健康度 | ✅ |
| `activity.py` | 核心 | 活动模式、bash 审计与执行统计 | ✅ |
| `session.py` | 核心 | 会话级聚合与安全审计摘要 | ✅ |

## 依赖关系

- `activity.py` → `common.py`
- `session.py` → `common.py`
- `tool_usage.py` → `common.py`
