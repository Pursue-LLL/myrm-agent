# compact/ — Chat context compaction implementation

## 架构概述

Server 业务层无损上下文压缩实现。`compact_service.py` 为对外 facade；本子包按职责拆分持久化、idle 估算、消息 IO、summarize 超时守卫与 `compact_chat` 入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `_constants.py` | 辅助 | 压缩/idle 阈值常量 | — |
| `_types.py` | 核心 | `CompactResult` | ✅ |
| `_lock.py` | 辅助 | 每 chat 并发锁 | ✅ |
| `service.py` | 核心 | `compact_chat`（circuit + anti-thrash + idle stale；`request_tokens_for_guard` 对齐 gate 口径） | ✅ |
| `persist.py` | 核心 | DB 持久化 + failure cooldown | ✅ |
| `compression_streak.py` | 核心 | Chat DB anti-thrash streak + harness store registration | ✅ |
| `idle_estimate.py` | 核心 | idle gate token 估算与 floor | ✅ |
| `message_io.py` | 辅助 | 消息加载/备份/LC 转换 | ✅ |
| `summarize_guard.py` | 辅助 | `/compact` 路径 progress 超时 | ✅ |
| `llm_config.py` | 辅助 | 用户模型 LLM 解析 | ✅ |
| `archive.py` | 辅助 | workspace 备份读取 | ✅ |

## 依赖

- harness：`summarize_circuit_guard`、`compression_anti_thrash_guard`、`generate_structured_summary`
- server：`Chat`/`Message` ORM、`ConversationRecallIndexService`
