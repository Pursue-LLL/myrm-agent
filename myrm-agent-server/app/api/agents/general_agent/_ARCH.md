# api/agents/general_agent/

## 架构概述

GeneralAgent 流式对话、重连与离线 durable 任务 HTTP 层。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | General Agent package. | ✅ |
| `active_sessions.py` | 模块 | attach SSE；pair auth 时校验 `require_mobile_pair_chat_access` | ✅ |
| `clarify.py` | 模块 | General Agent clarify 流式 API | ✅ |
| `media_config.py` | 模块 | 媒体生成配置连通性测试 | ✅ |
| `streaming.py` | 模块 | agent-stream / steer / chat cancel；pair auth 时校验 scoped chat 绑定 | ✅ |
| `suggestions.py` | 模块 | General Agent 建议 API | ✅ |
