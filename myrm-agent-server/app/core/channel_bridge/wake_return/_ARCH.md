# core/channel_bridge/wake_return/

## 架构概述

唤醒回合（后台任务或子智能体完成后，智能体在会话里自主跟进的一轮）与所有者 IM 私聊的两个接点：回合起之前，等所有者在这条私聊里正在跑的回合结束；回合说完之后，把说的话送回这条私聊。回合本身在 `services/agent/adaptive_wakeup/` 里跑，它只认识会话 id；会话来自哪个 IM 对话、IM 回合由谁在跑、怎么把话送到那里，只有渠道桥知道，所以回合经端口 `adaptive_wakeup/chat_busy.py` 问「这条私聊正在跑回合吗」、经端口 `adaptive_wakeup/reply_return.py` 把回复交出来，本包是 IM 一侧的实现。上级文档：[../_ARCH.md](../_ARCH.md)；回合一侧见 [../../../services/agent/adaptive_wakeup/_ARCH.md](../../../services/agent/adaptive_wakeup/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ChannelChatBusyProbe`、`ChannelWakeReplyReturner`、`WakeOrigins`、`get_wake_origins`、`register_wake_im_ports`、`clear_wake_im_ports` | ✅ |
| `origins.py` | 核心 | `WakeOrigins`：每个会话记最近一条 IM 消息（容量 256，写入最久的先丢，重写刷新）；记的是消息本身，因为会话行只存会话键，而会话键被清洗并转小写，还原不出渠道要用的 peer id。存入前去掉附件、引用上下文、续跑值与非字符串元数据，正文截到 500 字符（草稿审核最多展示这么多）；`web` / `chat` / `voice` 渠道不是可以回去的对话，不记。进程内存，重启即空：重启之后的唤醒回合只留在会话里。`get_wake_origins()` 是进程级实例 | ✅ |
| `busy_probe.py` | 核心 | `ChannelChatBusyProbe`：实现端口 `ChatBusyProbe`（同步，调度器在它回答之后的同一步里取会话，中间不能有 `await`）。查会话的来源消息，没有（不是 IM 私聊、或重启之后还没聊过）就是空闲；有则问网关 `is_session_busy(origin)`，即路由的会话闸门是否有回合在跑。IM 回合由路由的会话闸门串行，不经应用网关的会话占用，所以只问应用网关看不见所有者正在这条私聊里的回合 | ✅ |
| `returner.py` | 核心 | `ChannelWakeReplyReturner`：实现端口 `WakeReplyReturner`。查会话的来源消息，没有就什么都不做；有则先去掉模型可能照抄的安全边界标记（`strip_internal_markers`，与 IM 普通回复出门前一致），清完为空就不送；再按会话的工作区扫描回复里点名的工作区相对路径文件（沙箱内解析、跳过代码块；超限与压缩的提示与普通回复一致，只剩文件名时用「交付物已附上」一句话），文件作为附件随回复送出；扫描失败只记警告、回复照常以文本送出，会话没有工作区则不扫描。最后调 `ChannelGateway.deliver_followup(origin, content, media)`，由路由按普通回复的规则送出（静默过滤、网页接力按钮、话题草稿审核；送不出去只是返回 `False`）。扫描函数在调用时才导入：执行器包会导入本包来登记来源。只覆盖回复正文点名的文件，工具产出的截图与制品深链接不在其中 | ✅ |
| `wiring.py` | 核心 | `register_wake_im_ports(gateway)`：把承载方与探针一起登记到唤醒回合的两个端口，两者读同一份来源记忆；`clear_wake_im_ports()` 一起清除。由渠道桥的启动与停止调用，网关不在跑时端口不能留着 | ✅ |

## 边界

- 登记点是 `agent_executor/execute_preamble/preamble.py`：记忆范围确定之后，所有者私聊（`not memory_scope.is_compartment`）的非续跑回合登记。唤醒回合带着所有者的全部记忆，所以群聊与访客会话（运行在记忆隔离舱里）不登记，它们的唤醒回复只留在会话里。
- 承载方与探针的注册 / 清除是 `wiring.py` 的 `register_wake_im_ports` / `clear_wake_im_ports`，由 `setup.py` 调用：`start_channel_gateway` 在路由装配后注册，`stop_channel_gateway` 清除；网关没在跑时回复不离开应用，也没有 IM 回合可等。
- 探针只回答「所有者此刻有回合在跑」。路由闸门里排队的后续消息接在当前回合之后立即开始，期间一直算忙；只有刚到、还在防抖窗口（默认 300 ms）里、回合尚未开始的消息，探针会说空闲。
- 反方向（唤醒回合运行期间所有者在 IM 里发来的消息）不在本包处理：路由的会话闸门看不到唤醒回合（它占用的是应用网关的会话），这条消息的回合会与唤醒回合并行。
- 本包不管「该不该起唤醒回合」，也不复制路由的投递规则；唯一的投递入口是网关的 `deliver_followup`（实现于路由的 `pipeline/execution.py`）。

## 测试

- `tests/core/channel_bridge/test_wake_origins.py` — 记录内容、去掉的字段、不可回去的渠道、容量与淘汰
- `tests/core/channel_bridge/test_wake_reply_returner.py` — 有来源则送入对应对话，没有则不送，路由拒收不算错误，照抄的安全边界标记不进对话、只剩标记的回复不送；回复点名的工作区文件作为附件送出且路径不留在正文、只剩文件名时用一句话、工作区之外的路径不附、没有工作区按文本、扫描失败仍送文本
- `tests/core/channel_bridge/test_chat_busy_probe.py` — 路由在跑该对话的回合则忙、没有则空闲、没聊过的会话不问路由就空闲
- `tests/core/channel_bridge/test_execute_preamble_wake_origin.py` — 谁登记、谁不登记
- `tests/core/channel_bridge/test_wake_return_wiring.py` — 网关启动 / 停止与承载方、探针的注册 / 清除
- `tests/services/agent/adaptive_wakeup/test_wake_reply_to_im.py` — 从结算到渠道收到消息的整条链路（真实服务、调度、承载方、探针、网关、路由会话闸门、总线；模型与平台是替身）：唤醒等所有者的 IM 回合结束再回复、回合里读过的结果不再被重复说一遍、回复点名的工作区文件作为附件到达
