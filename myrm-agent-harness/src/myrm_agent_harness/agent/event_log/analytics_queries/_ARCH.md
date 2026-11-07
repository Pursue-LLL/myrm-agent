# agent/event_log/analytics_queries/

## 架构概述

EventLogger 的读侧查询按分析域拆分，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出全部查询函数 |
| `common.py` | 事件收集、时长与失败原因提取 |
| `tool_usage.py` | 工具使用统计、全局稳定性、单 Agent 健康度 |
| `activity.py` | 活动模式、bash 审计与执行统计 |
| `session.py` | 会话级聚合与安全审计摘要 |
