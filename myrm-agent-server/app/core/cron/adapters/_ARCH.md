# core/cron/adapters 模块架构


---

## 架构概述

Cron 定时任务系统的业务层适配器。将框架层的 CronStore / JobRunner / ResultDelivery 协议映射到应用层的具体实现（SQLAlchemy、Agent 管道、Channel Gateway）。`setup.py` 是唯一的组装入口。

在 Agent-in-Sandbox 架构下，每个沙箱是单 Worker，CronScheduler 不使用分布式锁。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `setup.py` | 组装入口：创建 CronScheduler + entitlement-guarded CronManager，注入所有适配器 |
| `entitlement_guarded_manager.py` | 包装 harness CronManager：`create_job` / `update_job` / `duplicate_job` 调用 `require_cron_slot`、``lifecycle_guard``、``tools_policy.normalize_cron_tools_allowed`` |
| `lifecycle_guard.py` | 拦截 cron prompt/command 中的 myrm restart/stop 等生命周期命令（防自杀 cron） |
| `tools_policy.py` | ``tools_allowed`` 规范化（保留 baseline 工具 ID）+ runtime 求交 + ``resolve_cron_runtime_tool_flags``（受限 job 不强制 baseline） |
| `sqlalchemy_store.py` | CronStore 协议的 SQLAlchemy 实现：Job/Run/MonitorState CRUD（`get_job` 路径对 legacy monitor_config 做 opportunistic 回写清洗，列表读取仅规范化映射不触发写入；启动阶段支持批量清洗并可设置批次数上限保护冷启动时延，返回结构化清洗统计与续清标记供可观测性收口） |
| `sqlalchemy_mapping.py` | ORM <-> Domain 双向映射（含 monitor_config 规范化） |
| `sqlalchemy_aggregation.py` | Token 用量聚合查询 |
| `python_condition.py` | PreFlightCondition 协议实现：SandboxedPythonCondition 在沙箱内安全执行前置探针脚本 |
| `agent_runner.py` | JobRunner 协议实现：通过 Agent 管道执行 cron 任务。始终以 `unattended_mode=True` 运行（跳过 ask_question_tool 工具注册 + 注入无人值守系统提示词），防止定时任务被 HITL 交互阻塞。当 CronJob.agent_id 存在时，通过 AgentProfileResolver 加载完整配置（含 `enabled_builtin_tools`、`auto_restore_domains`、`memory_decay_profile`、`cron_post_run_verify`），并通过 `resolve_builtin_tool_flags()` 统一映射 builtin 工具 flag（含 `enable_render_ui` 等），解析 agent/cron/chat 绑定的 Shared Context 注入 `memory_shared_context_ids`。**Post-run delivery verification**：Agent 流结束后、可选调用 `post_run_verification.apply_cron_post_run_verification()`（verifier-only，120s 超时；FAIL 不改变 run success，写入 `metadata.verification`）。**Thread Automation**：当 `session_target=MAIN` 且 `chat_id` 存在时，通过 `_load_thread_history` 加载目标会话的 compacted_summary + 近 30 条消息作为 `chat_history` 注入 Agent，实现定时任务的上下文连续性。**Heartbeat follow-up ack**：heartbeat 运行结束后调用 `_finalize_heartbeat_follow_up_delivery()`，按 `[SILENT]` 判定 SENT 或 snooze |
| `post_run_verification.py` | Cron 后置交付复核：当 Agent `cron_post_run_verify=true` 且 run 成功且检测到 mutating 工具使用时，spawn `adversarial-reviewer`（`verify_worker_output`，不重跑 worker）。effectful 工具 SSOT：`completion_guard.is_mutating_tool()` |
| `channel_delivery.py` | ResultDelivery 协议实现：IM 渠道投递 + Webhook；Feishu/Lark **bot hook** 走 `feishu_bot_webhook.py`；WeCom **bot hook** 走 `wecom_bot_webhook.py` |
| `delivery_resolver.py` | Cron 工具 webhook URL → `DeliveryConfig`（非空 URL 均为 `webhook` channel） |
| `feishu_bot_webhook.py` | Feishu/Lark 自定义机器人 hook：`msg_type=text` JSON POST |
| `wecom_bot_webhook.py` | WeCom (企业微信) 群机器人 hook：`msgtype=markdown` JSON POST |
| `inbound_event_dispatch.py` | 入站 IM 消息 → `CronScheduler.dispatch_event`（SSOT：`AgentRouter` 过滤后调用） |
| `sqlalchemy_trigger_provider.py` | TriggerProvider 实现：event/system/webhook 匹配 |
| `stream_listener.py` | StreamListener 实现：出站 WS/SSE 长连接管理（重连 + 心跳 + filter 匹配 + 资源限制） |
| `poll_listener.py` | PollListener 实现：定时 HTTP 拉取 + 内容哈希变更检测 |

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
