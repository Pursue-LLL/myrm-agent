# core/channel_bridge/executor_helpers/

## 架构概述

ChannelAgentExecutor 执行前后辅助能力。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公开 API 重导出 | ✅ |
| `history.py` | 模块 | 频道聊天历史持久化、标题生成；**入站新 turn 前 `run_pre_reply_stale_compact_gate`**；persist/resume 时 sync topic workspace；入站 user 消息持久化时把超大文本外溢到频道智能体实际运行的 JIT 工作区（`agent_workspace()`），智能体事后能读回；`persist_and_load_history` 同时登记「用户发言」，恢复自适应唤醒额度并解除停止压制 | ✅ |
| `agent_workspace.py` | 模块 | `agent_workspace(chat_id)`：频道聊天的智能体实际运行目录（JIT 工作区，纯路径计算不建目录；频道智能体参数不带绑定工作区，topic 绑定不影响它；不能命名目录的 id 返回 None）。给智能体停放文件的所有调用方（超大入站文本、参考文档）共用这一个答案 | ✅ |
| `topic_workspace_sync.py` | 模块 | Topic 绑定目录写入/清空 chat SSOT（project_id / workspace_dir） | ✅ |
| `stream.py` | 模块 | StreamAccumulator（回复文本 `draft` 是 harness 的 `AnswerDraft`：恢复重放只丢最近一次工具步骤之后的在途段落；含致命错误的原始文本 `error_message` 与错误类型 `error_kind`、loop guard 暂停了本回合的标记 `tool_stuck_paused`）、进度标签、ShareableArtifact | ✅ |
| `quick_replies.py` | 模块 | 快捷回复建议、externalAgents 解析 | ✅ |

## 测试

- `tests/core/channel_bridge/test_step_to_label.py`
- `tests/core/channel_bridge/test_stream_events.py`
- `tests/core/channel_bridge/test_executor_token_usage.py`
- `tests/core/channel_bridge/test_deliverable_deep_links.py`
- `tests/core/channel_bridge/test_channel_image_accumulator.py`
- `tests/core/channel_bridge/test_executor_helpers_history.py` — history 持久化 helper；超大入站文本外溢进智能体工作区（含与 harness 自行推导的工作区一致性的真库往返）
- `tests/core/channel_bridge/test_executor_helpers_agent_workspace.py` — 智能体工作区路径与 harness 实际创建的目录一致；不安全 id 返回 None
- `tests/core/channel_bridge/test_topic_workspace_sync.py` — topic workspace sync + effective_workspace 链
- `tests/core/channel_bridge/test_executor_helpers_stream.py` — stream accumulator / step_to_label
