# core/channel_bridge/wake_return/

## 架构概述

把唤醒回合（后台任务或子智能体完成后，智能体在会话里自主跟进的一轮）说的话送回所有者的 IM 私聊。回合本身在 `services/agent/adaptive_wakeup/` 里跑，它只认识会话 id；会话来自哪个 IM 对话、怎么把话送到那里，只有渠道桥知道，所以回合经端口 `adaptive_wakeup/reply_return.py` 把回复交出来，本包是 IM 一侧的承载方。上级文档：[../_ARCH.md](../_ARCH.md)；回合一侧见 [../../../services/agent/adaptive_wakeup/_ARCH.md](../../../services/agent/adaptive_wakeup/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ChannelWakeReplyReturner`、`WakeOrigins`、`get_wake_origins` | ✅ |
| `origins.py` | 核心 | `WakeOrigins`：每个会话记最近一条 IM 消息（容量 256，写入最久的先丢，重写刷新）；记的是消息本身，因为会话行只存会话键，而会话键被清洗并转小写，还原不出渠道要用的 peer id。存入前去掉附件、引用上下文、续跑值与非字符串元数据，正文截到 500 字符（草稿审核最多展示这么多）；`web` / `chat` / `voice` 渠道不是可以回去的对话，不记。进程内存，重启即空：重启之后的唤醒回合只留在会话里。`get_wake_origins()` 是进程级实例 | ✅ |
| `returner.py` | 核心 | `ChannelWakeReplyReturner`：实现端口 `WakeReplyReturner`。查会话的来源消息，没有就什么都不做；有则调 `ChannelGateway.deliver_followup`，由路由按普通回复的规则送出（静默过滤、网页接力按钮、话题草稿审核；送不出去只是返回 `False`） | ✅ |

## 边界

- 登记点是 `agent_executor/execute_preamble/preamble.py`：记忆范围确定之后，所有者私聊（`not memory_scope.is_compartment`）的非续跑回合登记。唤醒回合带着所有者的全部记忆，所以群聊与访客会话（运行在记忆隔离舱里）不登记，它们的唤醒回复只留在会话里。
- 承载方的注册 / 清除在 `setup.py`：`start_channel_gateway` 在路由装配后注册，`stop_channel_gateway` 清除；网关没在跑时回复不离开应用。
- 本包不管「该不该起唤醒回合」，也不复制路由的投递规则；唯一的投递入口是网关的 `deliver_followup`（实现于路由的 `pipeline/execution.py`）。

## 测试

- `tests/core/channel_bridge/test_wake_origins.py` — 记录内容、去掉的字段、不可回去的渠道、容量与淘汰
- `tests/core/channel_bridge/test_wake_reply_returner.py` — 有来源则送入对应对话，没有则不送，路由拒收不算错误
- `tests/core/channel_bridge/test_execute_preamble_wake_origin.py` — 谁登记、谁不登记
- `tests/core/channel_bridge/test_wake_return_wiring.py` — 网关启动 / 停止与承载方的注册 / 清除
- `tests/services/agent/adaptive_wakeup/test_wake_reply_to_im.py` — 从结算到渠道收到消息的整条链路（真实服务、调度、承载方、网关、路由、总线；模型与平台是替身）
