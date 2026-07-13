# core/channel_bridge/executor_helpers/

## 架构概述

ChannelAgentExecutor 执行前后辅助能力。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公开 API 重导出 | ✅ |
| `history.py` | 模块 | 频道聊天历史持久化、标题生成 | ✅ |
| `approval.py` | 模块 | 审批超时调度与超时结果通知 | ✅ |
| `stream.py` | 模块 | StreamAccumulator、进度标签、ShareableArtifact | ✅ |
| `quick_replies.py` | 模块 | 快捷回复建议、externalAgents 解析 | ✅ |

## 测试

- `tests/core/channel_bridge/test_step_to_label.py`
- `tests/core/channel_bridge/test_stream_events.py`
- `tests/core/channel_bridge/test_executor_token_usage.py`
- `tests/core/channel_bridge/test_artifact_deep_links.py`
- `tests/core/channel_bridge/test_channel_image_accumulator.py`
