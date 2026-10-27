# core/channel_bridge/goal_handler/

## 架构概述

IM 渠道的 `/goal` 与 `/subgoal` 命令处理器：把渠道消息解析到所属 Web 聊天，再经 `GoalRegistry` 的 provider 操作目标。
`__init__.py` 只导出 `ChannelGoalCommandHandler`，对外 import 路径保持 `app.core.channel_bridge.goal_handler`。
上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ChannelGoalCommandHandler` | ✅ |
| `handler.py` | 核心 | `ChannelGoalCommandHandler`：创建目标时注入 source channel metadata（channel/chat_id/thread_id/locale）供 `GoalTerminalNotifier` 闭环回推；`/goal clear` 与 Web 取消共用 `select_cancellable_goal`（暂停/预算受限/待复核/等待中的目标也能清除）；`/goal pause`/`/goal clear` 与 Web 一样中断正在干活的目标的回合（`stop_goal_turn`）；`/goal resume` 先等「已被要求停止」的回合收尾（`wait_for_stopped_turn`，等不到回复 `goal_resume_stopping` 且目标保持暂停），再恢复并经 `get_resume_kickoff_message` 让目标回到工作；`/goal unwait` 结束等待后同样经 `get_resume_kickoff_message` 让目标回到工作（与 Web unwait 一致）；全部静态回复走 channel i18n catalog | ✅ |
| `status_view.py` | 辅助 | `render_goal_status`：`/goal status` 的多行本地化回复（状态、预算、约束、验收标准、子目标），纯展示，不做 provider 查询 | ✅ |
| `chat_resolution.py` | 辅助 | `resolve_chat_id`：渠道消息 → 所属 Web 聊天 id（按 `SessionKey` 查最新聊天；尚无聊天返回 None） | ✅ |

## 测试

- `tests/core/channel_bridge/test_goal_resume_command.py` — `/goal resume` 等回合收尾、等不到时拒绝并保持暂停、不被无人叫停的在途回合拖住；`resolve_chat_id` 的 patch 点是 `goal_handler.handler.resolve_chat_id`
- `tests/core/channel_bridge/test_goal_stop_commands.py` — `/goal clear` / `/goal pause` 与 Web 取消同一批目标、同一次中断
- `tests/core/channel_bridge/test_goal_status_view.py` — `/goal status` 回复的各部分与顺序
- `tests/channels/test_goal_command.py` — 路由层对 handler 协议的调用
