# outbound_notify 模块架构

## 架构概述

Agent 点名投递的出站 Channel 通知：把 `notify_targets` 规范化成封闭的 `destination` 集合、会话级 rate limit、`ChannelGateway.bus.send_now` 同步投递并返回结果、媒体附件，以及可选 `channel_notify_tool` LangChain 适配器。

上级文档：[../_ARCH.md](../_ARCH.md)。

Agents 经 `app.ai_agents.general_agent.factory` → `factory_wiring.append_channel_notify_tool`（Turn1，`notify_targets` 里有可用的行且非只读安全模式时）挂载。投递失败经 `send_now` 结算（DLQ + `channel_bridge.handle_dead_letter`）后抛出，工具把原因回给模型。持久化 dedupe 见 `SqliteDeliveryNotifyLedger`（`state_dir/delivery_notify_ledger.db`）。子 Agent 不可继承 notify 工具（`register_leaf_blocked_tools`）。只读安全预设阻断出站工具挂载以防止数据泄密。

前端 recipient 选择：`GET /channels/manage/status`、`GET /channels/manage/pairings`。

## 目的地契约

- 工具只有一个必填选择：`destination`，是 `notify_targets` 规范化后的封闭枚举，写在工具参数模式里。名字是 `渠道:标签`；标签为空时取 `渠道#序号`（序号是该行在配置里的位置，从 1 起）；重名追加 `-2`、`-3`。
- 规范化在 `sender.create_notification_sender`：`channel` 或 `recipient_id` 缺失、为空或不是文本的行被丢弃（每行一条 WARNING，只写行序号，不写收件人）；标签去控制字符、合并连续空白、截 32 字；没有可用的行则不装载工具。
- 集合外的值、缺 `destination` 的调用（含只带 `channel`、`target` 的）由工具的参数校验拒绝，不发送；校验在审批之后执行，审批卡先显示模型给的原值。
- 审批卡里的参数就是 `destination`，所批即所发。聊天里每次发送都需人批准、没有「始终允许」，YOLO 会话同样暂停（`tests/services/agent/outbound_notify/test_channel_notify_approval_graph.py`）。
- 使用条件只写在工具说明里（含「点名的收件人不在目的地里、或对应多个目的地时先问用户」），系统提示不追加段落。
- `notify_targets` 只有点名投递这一个读取方。系统驱动的推送（如批处理完成）一律发布 `SYSTEM_NOTIFICATION` 事件，由 `NotificationDispatcher` 按用户的「通知投递」送达，不读这些目的地，也不经 `ChannelNotificationSender` 直发。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | NotifyTarget、NotifyToolConfig（`destinations` 封闭集合）、NotifyResult、NotifySessionState | ✅ |
| `constants.py` | 辅助 | `NOTIFY_SOURCE_AGENT`、`METADATA_KEY_NOTIFY_SOURCE` 元数据 SSOT | ✅ |
| `protocols.py` | 核心 | NotificationSender 协议（含 media） | ✅ |
| `sender.py` | 核心 | ChannelNotificationSender（`bus.send_now`）+ `create_notification_sender`（行规范化与目的地命名） | ✅ |
| `factory_wiring.py` | 核心 | `append_channel_notify_tool` — GeneralAgent Turn1 挂载 SSOT | ✅ |
| `attachment_path_policy.py` | 核心 | 本地附件路径守卫（agent `declared_allowed_roots`） | ✅ |
| `channel_notify_tool.py` | 适配器 | `create_channel_notify_tool` LangChain 工厂：`destination` 枚举入参、工具说明与守卫句 | ✅ |
| `__init__.py` | 入口 | 公共导出 | ✅ |

## 依赖关系

- `app.channels` — ChannelGateway、OutboundMessage、MediaAttachment
- `app.core.channel_bridge` — gateway 单例
