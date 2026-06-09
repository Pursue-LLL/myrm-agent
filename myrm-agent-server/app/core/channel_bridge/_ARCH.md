# core/channel_bridge 模块架构


---

## 架构概述

Channel 系统的业务适配层。基于 `app.channels` 的渠道框架协议（BaseChannel, ChannelGateway, PairingStore 等），提供声明式 Channel 绑定（23 个渠道）、凭证解析、Agent 执行、群组策略和话题配置能力。外部 IM provider 的本地扩展仅在 local mode 启用，core AgentRouter 在 local 和 Control Plane 两种模式下都装配，以保证 `/api/channel/message` 这条 sandbox 内部入口始终可用。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 入口 | 导出 `channel_gateway` 全局单例，并定义 `handle_dead_letter` 回调处理死信通知 | ❌ |
| `channel_factory.py` | ✅ 核心 | Channel 工厂，`create_all_channels()` 委托框架层 `create_channels` 实例化所有 Channel，`create_channel_instance()` 支持多实例并设置 `channel_type`/`display_name` 正式属性 | ✅ |
| `credential_spec.py` | ✅ 核心 | DB 凭证源：`load_from_db`（`CredentialSource` 回调）+ `is_channel_enabled`。凭证类型和 SPEC 常量已迁移到框架层各 Provider | ✅ |
| `setup.py` | ✅ 核心 | Gateway 生命周期管理：`start_channel_gateway` / `stop_channel_gateway`。注入 `handle_dead_letter` 回调，将底层死信事件转化为业务层的持久化通知和 SSE 推送；始终装配 core AgentRouter，本地模式再额外启用 WhatsApp/LID/默认用户策略等 local-only 扩展。`_restore_channel_instances()` 恢复持久化实例时使用 `channel.display_name` 正式属性。`_build_agent_route_commands()` 构建业务层 AGENT_ROUTE 命令。`_load_skill_command_bindings()` 从 DB 加载所有 AgentProfile.command_bindings 转为 SKILL 类型 CommandDef。`reload_skill_command_bindings()` 运行时热重载技能命令绑定（Agent CRUD 时由 agent_service 调用）。注入 `ChannelSkillCommandHandler` 处理技能绑定斜杠命令 | ✅ |
| `skill_command_handler.py` | ✅ 核心 | `ChannelSkillCommandHandler`：SkillCommandHandler 协议的业务层实现，将技能绑定的斜杠命令转换为 `[use skill_id]` 格式注入消息内容，复用前端相同的 Skill 触发约定 | ✅ |
| `config_loader.py` | ✅ 核心 | 用户配置加载层：从 UserConfig 表一次性加载模型/搜索/检索/MCP/语音等配置，30s TTL 缓存。`_resolve_override` 支持自定义 provider（通过 `providerType` 兼容匹配 + `enabledModels` 校验），`_to_litellm_model` 根据 `providerType` 生成正确的 LiteLLM 模型名。`register_custom_model_pricing` 将用户自定义模型定价注册到 litellm.model_cost | ✅ |
| `config_readiness.py` | ✅ 核心 | Provider配置完整性检查器：ProviderConfigChecker 继承框架层 ConfigReadinessChecker，检查用户是否配置了至少一个已启用且有效的 provider，区分本地provider（Ollama/LM Studio）和API provider的检查逻辑 | ✅ |
| `config_parsers.py` | ✅ 核心 | 配置解析器：从前端 dict 结构解析为类型化配置对象（SearchServiceConfig、SessionPolicy、TTSMode 等）。`session_policy_from_agent_dict` 支持 per-agent 会话策略覆盖。提供 `verify_search_service_available`（SearXNG HTTP 连通性检查，30s TTL 缓存）和 `invalidate_search_health_cache`（配置变更时清除缓存） | ✅ |
| `config_cache.py` | ✅ 辅助 | 用户配置 TTL 缓存：30s 过期的内存缓存，通过 `invalidate_user_configs_cache()` 支持配置更新后即时失效 | ✅ |
| `agent_executor/executor.py` | ✅ 核心 | `ChannelAgentExecutor`：映射框架 AgentExecutor→业务 GeneralAgent；流式/持久化、reasoning/tool_steps 累积、审批超时、YOLO、Personality、`ConfigIncompleteError` i18n；搜索可达性门禁；优先 `resolved_identity` 记忆边界，透传 thread/epoch 元数据、`memory_shared_context_ids`/`Shared Context`；`build_channel_inbound_query` 构建渠道 Human 输入（支持多模态图片+文本+ReplyContext 引用注入），加投递横幅并保持群上下文装配。详情见 `agent_executor/_ARCH.md` | ✅ |
| `executor_helpers.py` | ✅ 辅助 | ChannelAgentExecutor 的辅助模块：历史持久化、标题生成、审批超时调度、流式累积（含 tool_image_output 图片缓存）、快速回复建议、进度标签转换、聊天历史格式化 | ✅ |
| `personality_adapter.py` | ✅ 辅助 | AppPersonalityProvider：业务层 PersonalityTemplate 到框架层 PersonalityProvider 协议的适配器，注入到 AgentRouter 供 /personality 命令使用 | ❌ |
| `model_resolver.py` | ✅ 核心 | 模型配置解析、上下文窗口自动填充和自定义定价注册：从 providers config 解析 ModelConfig，通过 `enrich_model_context_window()` 自动查询 customModelInfo 或 litellm 获取模型真实 max_input_tokens 并填充 `max_context_tokens`，当 providers 缺失或无有效配置时抛出 ConfigIncompleteError（携带中英双语友好消息和解决方案步骤），支持自定义 provider 类型和模型定价注册 | ✅ |
| `channel_policy.py` | ✅ 核心 | SqlChannelPolicyProvider：从 UserConfig 读取 DM/群聊策略、群组启用列表、Telegram guestMode（telegramCredentials）。单租户模式下默认查询 channels 配置 | ✅ |
| `pairing_store.py` | ✅ 核心 | SqlPairingStore：PairingStore 协议的 SQLAlchemy 实现，管理 sender → user 绑定。新建 PENDING 配对时通过 EventBus 发布 `PAIRING_PENDING` 事件 | ✅ |
| `topic_config.py` | ✅ 核心 | SqlTopicManager：TopicManager 协议实现，读写 per-topic 配置（resolve/bind/unbind, agent_id, enabled, bound_at）。包含 sync_topic_metadata 支持群组/话题元数据自动发现 | ✅ |
| `background_task_handler.py` | ✅ 核心 | ChannelBackgroundTaskHandler：BackgroundTaskHandler 协议的业务层实现。管理 /background (/btw /bg) 命令触发的后台任务生命周期（spawn/list/cancel/steer），通过 Kanban 系统持久化任务状态，具备重启恢复和僵尸检测。cancel 时通过 KanbanService.cancel_task_execution 即时取消 asyncio 执行。维护内存级 CancellationToken/SteeringToken 用于运行时控制 | ✅ |
| `status_handler.py` | ✅ 核心 | ChannelStatusProvider：StatusProvider 协议的业务层实现。查询最近的 Chat 会话元数据（session_id、title、tokens、model、created_at、last_activity）供 /status 命令显示 | ✅ |
| `locale_provider.py` | ✅ 核心 | UserConfigLocaleProvider：LocaleProvider 协议实现，从 `personalSettings.locale` 解析用户语言偏好并注入渠道 slash 命令 i18n | ✅ |
| `goal_handler.py` | ✅ 核心 | ChannelGoalCommandHandler：/goal 与 /subgoal 业务处理器，全部静态回复走 harness channel i18n catalog | ✅ |

### 子目录

| 模块 | 职责 | 文档 |
|------|------|------|
| `providers/` | 业务层 Channel 实现（仅 ChatChannel）及辅助 API 客户端。所有通用 IM 通道已内置于框架层 | [_ARCH.md](providers/_ARCH.md) |

---

## 数据流

```
外部平台 Webhook → api/channels/webhook.py
                       ↓
                  BaseChannel.handle_webhook()
                       ↓
              ChannelGateway (AgentRouter)
                       ↓
        SqlPairingStore.resolve() -> policy
        SqlChannelPolicyProvider → DM/群聊策略
        SqlTopicManager → 话题级路由 + 绑定管理
                       ↓
          ChannelAgentExecutor.execute_stream()
                       ↓
              config_loader → 用户配置
              AgentFactory → Agent 实例
                       ↓
          ProgressUpdate / StreamingText / OutboundMessage
                       ↓
              BaseChannel.send_message()
```

Control Plane 模式下还会额外走一条内部入口：

```
Control Plane Dispatcher
        ↓ HTTP
/api/channel/message
        ↓
InboundMessage(resolved_identity + thread_id + force_new_epoch)
        ↓
ChannelGateway / AgentRouter / ChannelAgentExecutor
```

其中内部入口会额外打上 `metadata["trusted_inbound"] = "control_plane"`。
这表示外部身份解析、thread/task 绑定和基础触发门控已经在 CP 边界完成，
Router 不再把这类消息误当成本地 provider 直接上送的原始 inbound。

`ChannelAgentExecutor.execute_stream()` 在进入模型前会通过 `agent_executor/helpers.py::build_channel_inbound_query`（`delivery_provenance.prepend_plain_banner`）构建查询：纯文本消息返回带 `[Inbound channel message] … ingress=…` 横幅的字符串；当 Harness 图片富化写入 `metadata["image_data_list"]` 时返回 OpenAI Vision 兼容的多模态 content list。把投递路径显式写给模型但不写入 System Prompt，以降低「路由元数据当成超级用户指令」的风险。

HTTP/SSE 主链路在 `execute_stream_pipeline` 内 **INFO 记录解析后的投递标签**，再对用户 Human `apply_delivery_banner`；还包括 **Headless wakeup**（见 `services/agent/_ARCH.md::wakeup_handler`）等对 `GeneralAgent.channel_name` 的信任链。

---

## 话题内会话共享（Thread Sharing Mode）

### 功能概述

`thread_sharing_mode` 是 `TopicContext` 的一个配置项，用于控制话题内的会话历史隔离策略：

- **`isolated`（默认）**：每个用户拥有独立的对话历史，适合普通 DM 或个人使用场景。
- **`shared`**：话题内所有用户共享同一对话历史，适合协作场景（如 Discord Forum、Telegram Forum Topic）。

### 实现原理

当 `thread_sharing_mode="shared"` 时，`_build_session_key()` 会将 `SessionKey` 的 `thread_id` 设为统一个值，从而让所有用户在同一话题中访问相同的 Chat 记录：

```python
# agent_executor.py
def _build_session_key(..., thread_sharing_mode: str = "isolated"):
    # Pseudo-code logic for SessionKey without user identifier
    sk = SessionKey(thread_id=effective_thread_id, ...)
```

### 使用场景

| 场景 | 推荐模式 | 说明 |
|------|----------|------|
| Discord Forum Post | shared | 论坛帖子内的多个用户协作讨论同一主题 |
| Telegram Forum Topic | shared | 话题内共享上下文，便于团队协作 |
| 普通群聊 | isolated | 每个用户有独立的对话历史 |
| 私聊 DM | isolated | 默认隔离，无需配置 |

### 前端配置

在「设置 → 渠道路由」页面，每个 Topic 可单独配置共享模式，支持实时切换。

---

## 依赖关系

### 内部依赖
- `providers/`：各平台 Channel 实现
- `../../database/`：UserConfig, ChannelPairingModel ORM
- `../../ai_agents/`：AgentFactory, GeneralAgentParams
- `../../services/chat/`：ChatService（对话持久化）

### 渠道框架依赖（app.channels）
- `app.channels`：BaseChannel, ChannelGateway
- `app.channels.protocols`：PairingStore, AgentExecutor, PolicyProvider
- `app.channels.types`：InboundMessage, OutboundMessage, SessionKey

### 外部依赖
- `sqlalchemy`：ORM 查询
- `nanoid`：ID 生成
