# stream_session/lanes 模块架构

## 架构概述

Chat 专用零 LLM 或轻量 SSE lane 实现，与 `stream_lane_factory.py` 中的 Fast Lane / Deep Research 等工厂并列，由 `stream_loop.py` 按准入规则路由。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `wiki_knowledge_lane.py` | 核心 | Wiki Knowledge Quick Lane：`SOURCES` + `MESSAGE` + `execution_lane=wiki_knowledge` | ✅ |

## 依赖关系

- `app/services/wiki/knowledge_query_service.py` — 检索 SSOT
- `app/services/wiki/wiki_query_intent.py` — Chat 准入闸门（由 `stream_loop.py` 调用）
