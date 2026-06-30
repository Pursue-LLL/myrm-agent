# core/cron/adapters 模块架构


---

## 架构概述

Cron 定时任务系统的业务层适配器。将框架层的 CronStore / JobRunner / ResultDelivery 协议映射到应用层的具体实现（SQLAlchemy、Agent 管道、Channel Gateway）。`setup.py` 是唯一的组装入口。

在 Agent-in-Sandbox 架构下，每个沙箱是单 Worker，CronScheduler 不使用分布式锁。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `setup.py` | 组装入口：创建 CronScheduler + CronManager，注入所有适配器 |
| `sqlalchemy_store.py` | CronStore 协议的 SQLAlchemy 实现：Job/Run/MonitorState CRUD |
| `sqlalchemy_mapping.py` | ORM <-> Domain 双向映射 |
| `sqlalchemy_aggregation.py` | Token 用量聚合查询 |
| `python_condition.py` | PreFlightCondition 协议实现：SandboxedPythonCondition 在沙箱内安全执行前置探针脚本 |
| `agent_runner.py` | JobRunner 协议实现：通过 Agent 管道执行 cron 任务。始终以 `unattended_mode=True` 运行（跳过 ask_question_tool 工具注册 + 注入无人值守系统提示词），防止定时任务被 HITL 交互阻塞。当 CronJob.agent_id 存在时，通过 AgentProfileResolver 加载完整配置（含 `enabled_builtin_tools`、`auto_restore_domains`、`memory_decay_profile`），并通过 `resolve_builtin_tool_flags()` 统一映射 builtin 工具 flag（含 `enable_render_ui` 等），解析 agent/cron/chat 绑定的 Shared Context 注入 `memory_shared_context_ids`。**Thread Automation**：当 `session_target=MAIN` 且 `chat_id` 存在时，通过 `_load_thread_history` 加载目标会话的 compacted_summary + 近 30 条消息作为 `chat_history` 注入 Agent，实现定时任务的上下文连续性。**Heartbeat follow-up ack**：heartbeat 运行结束后调用 `_finalize_heartbeat_follow_up_delivery()`，按 `[SILENT]` 判定 SENT 或 snooze |
| `channel_delivery.py` | ResultDelivery 协议实现：IM 渠道投递 + Webhook；Feishu/Lark **bot hook** 走 `feishu_bot_webhook.py` |
| `delivery_resolver.py` | Cron 工具 webhook URL → `DeliveryConfig`（非空 URL 均为 `webhook` channel） |
| `feishu_bot_webhook.py` | Feishu/Lark 自定义机器人 hook：`msg_type=text` JSON POST |
| `inbound_event_dispatch.py` | 入站 IM 消息 → `CronScheduler.dispatch_event`（local MessageBus 与 Control Plane ingress 共用） |
| `sqlalchemy_trigger_provider.py` | TriggerProvider 实现：event/system/webhook 匹配 |

---

## 依赖关系

### 内部依赖
- `myrm_agent_harness.toolkits.cron`：CronManager, CronScheduler, WebhookDelivery, 协议定义
- `../../channels/`：ChannelGateway（channel_delivery 使用）
- `../../channels/config_loader`：用户配置加载（agent_runner 使用）
- `../../../ai_agents/`：AgentFactory（agent_runner 使用）
- `../../../services/agent/profile_resolver`：AgentProfileResolver（agent_runner 使用，agent_id 绑定时加载完整配置）
- `../../../services/chat/chat_service`：`ChatService.load_web_chat_history`（agent_runner 使用，Thread Automation 模式加载会话历史）
- `../../../services/memory/shared_context`：Shared Context 绑定解析（agent_runner 使用）
- `../../../database/`：CronJob / CronRun ORM

### 外部依赖
- `sqlalchemy`：ORM 操作
