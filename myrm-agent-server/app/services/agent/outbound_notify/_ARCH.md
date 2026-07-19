# outbound_notify 模块架构

## 架构概述

Agent 主动出站 Channel 通知：类型、白名单 target 解析、会话级 rate limit、`ChannelGateway.bus.send_tracked` 可靠投递、媒体附件，以及可选 `channel_notify_tool` LangChain 适配器。

上级文档：[../_ARCH.md](../_ARCH.md)。

Agents 经 `app.ai_agents.general_agent.factory` → `factory_wiring.append_channel_notify_tool`（Turn1，`notify_targets` 配置时）挂载。投递失败经 DLQ + `channel_bridge.handle_dead_letter` 闭环。持久化 dedupe 见 `SqliteDeliveryNotifyLedger`（`state_dir/delivery_notify_ledger.db`）。子 Agent 不可继承 notify 工具（`register_leaf_blocked_tools`）。

前端 recipient 选择：`GET /channels/manage/status`、`GET /channels/manage/pairings`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | NotifyTarget、NotifyToolConfig、NotifyResult、NotifySessionState | ✅ |
| `constants.py` | 辅助 | `NOTIFY_SOURCE_AGENT`、`METADATA_KEY_NOTIFY_SOURCE` 元数据 SSOT | ✅ |
| `protocols.py` | 核心 | NotificationSender 协议（含 media） | ✅ |
| `target_resolver.py` | 核心 | `resolve_notify_target` 白名单解析 | ✅ |
| `sender.py` | 核心 | ChannelNotificationSender + `create_notification_sender`；`bus.send_tracked` 可靠投递 | ✅ |
| `factory_wiring.py` | 核心 | `append_channel_notify_tool` — GeneralAgent Turn1 挂载 SSOT | ✅ |
| `attachment_path_policy.py` | 核心 | 本地附件路径守卫（agent `declared_allowed_roots`） | ✅ |
| `channel_notify_tool.py` | 适配器 | `create_channel_notify_tool` LangChain 工厂 | ✅ |
| `__init__.py` | 入口 | 公共导出 | ✅ |

## 依赖关系

- `app.channels` — ChannelGateway、OutboundMessage、MediaAttachment
- `app.core.channel_bridge` — gateway 单例
