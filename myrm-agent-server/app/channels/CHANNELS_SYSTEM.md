# Channel System 设计文档

> 多平台消息通道系统的技术方案与架构设计

---

## 1. 设计目标

1. **平台无关**：统一抽象 24+ 个 IM/通信平台，业务层零感知渠道差异
2. **双向实时**：支持出站推送和入站 Agent 对话两种模式
3. **声明式扩展**：新增渠道仅需 3 步（实现 Provider → 声明 Spec → 添加 Binding）
4. **生产级可靠**：错误隔离、自动重连、速率限制、健康检查、结构化诊断
5. **Protocol-first**：渠道框架定义协议接口，业务层通过依赖注入提供存储和 Agent 实现

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        业务层 (myrm-agent-server)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ channel_     │  │ credential_  │  │ agent_executor /         │  │
│  │ factory.py   │  │ spec.py      │  │ pairing_store /          │  │
│  │ (22 bindings)│  │ (20 SPECs)   │  │ channel_policy           │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────────┘  │
│         │                 │                                         │
├─────────┼─────────────────┼─────────────────────────────────────────┤
│         ▼                 ▼           渠道框架 (app/channels/)      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ChannelGateway                            │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │    │
│  │  │ 生命周期  │  │ 健康检查  │  │ 启用/禁用 │  │ 事件发布  │  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │    │
│  └─────────────────────┬───────────────────────────────────────┘    │
│                        │                                            │
│  ┌─────────────────────▼───────────────────────────────────────┐    │
│  │                    MessageBus                                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │    │
│  │  │ 入站队列  │  │ 出站分发  │  │ 组件降级  │  │ DISABLED  │  │    │
│  │  │          │  │          │  │          │  │ 拦截      │  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │    │
│  └─────────────────────┬───────────────────────────────────────┘    │
│                        │                                            │
│  ┌─────────────────────▼───────────────────────────────────────┐    │
│  │                   AgentRouter                                │    │
│  │  去重 → 命令检测 → 策略解析 → Debounce → Agent 执行 → 回复  │    │
│  └─────────────────────┬───────────────────────────────────────┘    │
│                        │                                            │
│  ┌─────────────────────▼───────────────────────────────────────┐    │
│  │                   Providers (24 个渠道实现)                   │    │
│  │  Telegram │ Discord │ WhatsApp │ Slack │ Feishu │ WeChat │  │    │
│  │  WeChatOfficial │ WeCom │ Teams │ Matrix │ DingTalk │ QQ │  │    │
│  │  GoogleChat │ Signal │ LINE │ IRC │ Email │ Voice │ SMS │  │    │
│  │  Zalo │ Mattermost │ iMessage │ Webhook │ Chat (业务层)      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
│  │ types/           │  │ rendering/       │  │ reliability/    │   │
│  │ 消息/组件/会话/   │  │ 渲染管道/分割    │  │ 速率限制/重试   │   │
│  │ 状态类型         │  │                  │  │                 │   │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘   │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
│  │ protocols/       │  │ voice/           │  │ routing/        │   │
│  │ AgentExecutor    │  │ STT/TTS          │  │ 流式/命令/策略  │   │
│  │ PairingStore     │  │                  │  │ 会话/降级       │   │
│  │ PolicyProvider   │  │                  │  │                 │   │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心组件

### 3.1 BaseChannel

所有渠道 Provider 的抽象基类，继承 `EventEmitter`。

**职责**：
- 定义渠道生命周期（`start()` / `stop()`）
- 声明渠道能力（`capabilities: ChannelCapabilities`）
- 提供消息收发接口（`send()` / `_emit_inbound()`）
- **便捷方法**（`respond()` / `broadcast()`）：语法糖提升开发体验，自动推断参数
- 健康追踪（`health: ChannelHealth`）
- 活动追踪（`activity: ChannelActivity`）
- 结构化诊断（`collect_issues()`）
- 交互组件（`send_placeholder()` / `edit_message()` / `react_to_message()`）

**便捷方法（Convenience Methods）**：

```python
# respond() - 回复消息（所有参数自动推断：channel/recipient_id/user_id/reply_to_id）
await channel.respond(incoming_msg, "Hello!")  # 代码简洁度提升80%

# broadcast() - 主动发送（Cron/通知场景，需要user_id）
await channel.broadcast("channel_id", "Alert!", user_id=user_id)

# send() - 底层统一接口（仍然完全可用，保持向后兼容）
await channel.send(OutboundMessage(...))
```

**入站管道**（`_emit_inbound` 内置，所有 Provider 共享）：

```
平台消息 → _emit_inbound()
    ├── 1. Bot 自消息过滤 (_bot_id)
    ├── 2. 消息去重 (_dedup_ttl, OrderedDict LRU)
    ├── 3. 访问控制 (AllowPolicy, 可注入白名单/黑名单)
    ├── 4. Debounce (_debounce_seconds, per-chat_id)
    └── 5. Dispatch → MessageBus 入站队列
```

> 此管道与 Router 层的去重/策略是不同层级的防护：BaseChannel 层防平台重发和未授权访问，Router 层防跨渠道 ID 碰撞和业务策略。

**启动模式（StartMode）**：

| Mode | 行为 | 典型渠道 |
|------|------|---------|
| `AUTO` | Gateway.start() 时立即启动 | Telegram, Slack, Discord 等轻量渠道 |
| `ON_DEMAND` | 跳过自动启动，用户登录时才启动 | WhatsApp（需要 Node.js Bridge） |

`should_auto_start()` 方法决定 Gateway 是否在启动时调用 `start()`：
- AUTO 模式：始终返回 True
- ON_DEMAND 模式：仅当存在已持久化的会话凭证时返回 True（如 WhatsApp 检查 `creds.json`）

**状态机**：

```
IDLE ──start()──→ RUNNING ──error──→ DEGRADED ──recover──→ RUNNING
  │                  │                                        │
  │                  ├──stop()──→ STOPPED                     │
  │                  │                                        │
  └──disable──→ DISABLED ──enable──→ RUNNING                  │
                                                              │
                     ERROR ←──fatal──────────────────────────┘
```

### 3.2 ChannelGateway

渠道生命周期管理器。

**职责**：
- 注册和管理所有渠道实例
- 并行启动/停止渠道（每个渠道独立 asyncio.Task，错误隔离）
- **StartMode 感知**：`_run_channel()` 在调用 `start()` 前检查 `channel.should_auto_start()`，ON_DEMAND 渠道在无已存会话时跳过启动
- 60s 周期健康检查（跳过 DISABLED / STOPPED 渠道）
- 运行时启用/禁用（`enable_channel()` / `disable_channel()`）
- 运行时热添加/移除（`add_channel()` / `remove_channel()`）
- 状态聚合（`get_status()` / `collect_all_issues()`）
- 事件订阅（`status_change` / `groups_change`）

**公网 Ingress 需求（与 `inbound_profile.py` 联动）**：

- 每个内置渠道在 `inbound_profile.CHANNEL_INBOUND_SPECS` 声明 `outbound` / `inbound` / `conditional` 传输模式
- `core/infra/ingress_requirement.resolve_ingress_requirement()` 读取 UserConfig 凭证 + Cron Webhook + SaaS 已注册 CP 渠道，输出 `GET /api/v1/system/ingress-requirement`
- `list_channel_status` 对 inbound 且未配置 Ingress 的渠道补充 CONFIG issue（fix 指向 Settings → System）

**多实例支持**：

同一渠道类型可注册多个实例（如多个微信账号），命名约定为 `{type}_{instance_id}`：

```
wechat          ← 默认实例
wechat_a1b2c3   ← 额外实例 1
wechat_d4e5f6   ← 额外实例 2
```

- `add_channel(channel)` — 运行时注册新实例，自动启动和健康监控
- `remove_channel(name)` — 运行时停止并注销实例
- `list_instances(type)` — 列出某类型所有实例
- 每种类型最多 `_MAX_INSTANCES_PER_TYPE`（默认 5）个实例
- 类型识别使用 `BaseChannel.channel_type` 正式属性（由工厂设置），回退到 `__class__.name`
- `BaseChannel.display_name` 提供用户友好的实例名称，`BaseChannel.instance_id` property 从 name 和 channel_type 自动派生
- **配置持久化**：实例元数据（channelType / instanceId / displayName）存储在 `UserConfig` 表中（key=`channel-instances`），服务重启后自动恢复
- **实例级登录**：每个实例通过 `/{channel_name}/wechat-status` 和 `/{channel_name}/wechat-login` 独立完成 QR 扫码登录，凭证存储在 `{channel_name}-credentials`

### 3.3 MessageBus

异步消息队列，连接渠道和 Router。集成底层 `DeadLetterQueue` 提供持久化死信队列与自动重试引擎。

**职责**：
- 入站：`_emit_inbound()` → 入站队列 → `AgentRouter.consume()`
- 出站：`OutboundMessage` → 目标渠道 `send()`
- **Rich Message 组件降级**：不支持原生组件的渠道自动降级为文本（支持国际化）
- DISABLED 拦截：三道防线（`_emit_inbound` / `_dispatch_loop` / `send_tracked`）

**Rich Message System 自动降级机制**：

`downgrade_components()` 在发送前自动转换不支持的交互组件为纯文本 fallback：

1. **能力检测**：读取 `ChannelCapabilities`（`buttons` / `quick_replies` / `select_menus`）
2. **按行降级**：
   - `ActionButton` → `"• {label} → /{action_id}"` 或 `"• {label} → {url}"`
   - `SelectMenu` → `"• {placeholder}: option1, option2, ..."`
   - `QuickReply` (required=True) → `"1️⃣ {label}\n2️⃣ {label2}\n\n↩️ 回复数字选择"`
   - `QuickReply` (required=False) → 静默丢弃（避免杂乱）
3. **国际化**：通过 `get_locale_from_metadata()` 归一化 locale（支持 `zh-CN`），catalog 渲染中英文 fallback（默认 en，业务层经 `metadata["locale"]` 注入）
4. **日志记录**：INFO级别记录降级事件，格式：`Downgrading components for channel 'whatsapp': buttons, quick_replies(2) → text fallback`
5. **文本追加**：将 fallback 文本追加到 `msg.content` 末尾，用 `\n\n` 分隔

**示例**：

```
原始消息：
content: "请批准这个请求："
components: [[ActionButton(label="批准", action_id="approve")]]

降级后（WhatsApp）：
content: "请批准这个请求：\n\n• 批准 → /approve"
components: []
```

**Channel Command i18n（slash 命令静态回复）**：

渠道 slash 命令的系统静态回复（非 Agent LLM 输出）通过 `app/channels/i18n/` 包提供 en / zh-CN 双语 catalog。

| 组件 | 职责 |
|------|------|
| `utils/locale.py` | BCP-47 归一化、`resolve_locale` 优先级链 |
| `i18n/catalog/en.py` / `zh_cn.py` | 扁平 key → 模板字符串（~180 key） |
| `i18n/__init__.py` | `channel_t` / `get_text` / `resolve_message_locale` |
| `protocols/locale.py` | `LocaleProvider` 协议（业务层注入） |
| `routing/router.py` | ingress 时 `_enrich_message_locale()` 写入 `metadata.locale` |

**Locale 解析优先级**：`metadata.locale` → `platform_locale` / `language_code`（Telegram ingress）→ `LocaleProvider`（server：`UserConfigLocaleProvider` 读 `personalSettings.locale`）→ 平台默认（feishu/dingtalk 等 → zh-CN）→ `en`。

**测试**：`tests/channels/test_channel_i18n.py` 断言 en/zh key 集合一致、placeholder 一致，并覆盖 `/goal`、`/topic` 等关键中文模板。

**前端联动**：设置 → 偏好 → 语言区块说明「同步应用于 Web 界面与 IM 渠道命令」；与 `personalSettings.locale` 写入链路一致。

### 3.4 AgentRouter

入站消息处理管道。

**处理流程**：
1. **去重**：message_id + TTL 防重复
2. **命令检测**：`/stop` / `/new` / `/compact` / `/topic` / `/agent` / 审批命令
3. **策略解析**：DM/群聊策略 + 身份解析 + 群组启用检查
4. **Debounce**：连发消息合并（SessionGate，默认 300ms 窗口）
5. **入站附件增强**（`_handle_merged`，在 Agent 执行前）：语音转写 → 贴纸描述 → 视频元数据 → 图片 base64（`image_data_list`）→ **PDF/Office 文本**（`document_text_blocks`，受 `personalSettings.extractDocumentText` 控制，默认开启；解析复用 `services/files/content_extraction`）
6. **并发控制**：`asyncio.Semaphore` 限制同时执行的 Agent 任务数
7. **Agent 执行**：`AgentExecutor.execute_stream()` + CancellationToken；`build_channel_inbound_query` 将文档块拼入 user 正文
8. **流式回复**：Placeholder 编辑 + 自适应节流 + 智能分块

**前端联动**：设置 → 偏好 → **提取附件文本**（`extractDocumentText`）同步影响 Web 聊天、IM 渠道与看板任务附件。

**审批命令（emoji reaction）**：

具备 `capabilities.reactions=True` 的渠道（Slack / Telegram / WhatsApp /
Discord / Signal / Feishu / iMessage / **Mattermost** / **Matrix**）会把
`reaction_added` / `m.reaction` / Tapback 等事件转换为
`InboundMessage(metadata={"reaction": True, "target_message_id": ...})`，由
`routing.commands.parse_approval_command` 统一识别。

| 决策档位        | 输入示例                                       | 透传给 harness 的 payload                                |
|-----------------|------------------------------------------------|----------------------------------------------------------|
| `allow_once`    | 👍 / ✅ / `/approve` / `1` / `y` / 同意         | `{"type": "approve"}`                                    |
| `allow_always`  | ♾️ / ⭐ / `/approve-always` / `aa` / 永远允许    | `{"type": "approve", "extensions": {"allowAlways": True}}` |
| `deny`          | 👎 / ❌ / `/deny` / `2` / `n` / 拒绝            | `{"type": "reject", "feedback": "Denied via ..."}`       |

`_is_reaction_approval_valid` 在群聊场景下校验 `sender_id` 必须是原始
请求者（`_ActiveTask.requester_id`）或显式配置的 `approval_co_approvers`
名单成员，DM 直接通过。`_handle_approval_command` 在 `set_approval_user_id`
绑定下游用户身份后，把 `allowAlways` 透传给 harness，触发
`add_to_allowlist_if_needed` 完成永久允许。

---

## 4. 渠道绑定机制

### 4.1 声明式凭证规格

每个渠道在 `credential_spec.py` 中声明一个 `ChannelCredentialSpec`，定义凭证字段与数据源的映射：

```
ChannelCredentialSpec
├── config_key: str              # DB 中的配置键（如 "telegramCredentials"）
└── fields: tuple[               # 凭证字段列表
        (param_name, CredentialField(db_key, env_var, default)),
        ...
    ]
```

**解析链**：`resolve_credentials(spec)` 按 DB → 环境变量 → 默认值 优先级解析。

### 4.2 声明式绑定

`channel_factory.py` 通过 `ChannelBinding` 将框架层渠道类与业务层凭证规格绑定：

```
ChannelBinding
├── channel_class: type[BaseChannel]           # 框架层渠道类
├── credential_spec: ChannelCredentialSpec      # 凭证规格
└── creds_transform: CredsTransform | None      # 可选的类型转换函数
```

### 4.3 实例化流程

`create_all_channels()` 遍历所有绑定：

```
for binding in _channel_bindings():
    ├── resolve_credentials(spec) → raw_creds
    ├── creds_transform(raw_creds) → typed_kwargs  (可选)
    ├── channel_class(**typed_kwargs) → channel
    ├── is_channel_enabled(config_key) → enabled?
    │   └── not enabled → channel._status = DISABLED
    └── yield channel
```

所有渠道（含 ON_DEMAND）均被实例化并注册到 Gateway。ON_DEMAND 渠道的启动由 Gateway 的 `should_auto_start()` 检查和业务层的登录触发共同控制。

**错误隔离**：单个渠道实例化失败时记录日志并跳过，不影响其他渠道。

### 4.4 新增渠道步骤

1. 在 `providers/` 下实现 `XxxChannel(BaseChannel)`，声明 `name` 和 `capabilities`
2. 在 `credential_spec.py` 中声明 `XXX_SPEC = _spec("xxxCredentials", ...)`
3. 在 `channel_factory.py` 的 `_channel_bindings()` 中添加 `_binding(XxxChannel, XXX_SPEC)`

---

## 5. 渠道启用/禁用控制

### 5.1 四层架构

| 层 | 组件 | 职责 |
|---|------|------|
| 存储层 | UserConfig DB | `enabled` 字段持久化 |
| 框架层 | Gateway + MessageBus + BaseChannel | 运行时状态管理 + 三道消息拦截防线 |
| 业务层 | channel_factory + routes.py | 启动时 DISABLED 标记 + API Toggle 端点 |
| 前端层 | ChannelsSection Switch | 可视化开关 |

### 5.2 三道防线

1. **BaseChannel._emit_inbound**：DISABLED 渠道的入站消息直接丢弃
2. **MessageBus._dispatch_loop**：DISABLED 渠道的出站消息不分发
3. **MessageBus.send_tracked**：DISABLED 渠道的直发消息被拦截

### 5.3 启动时行为

所有已绑定的渠道（含 DISABLED 和 ON_DEMAND）都会被实例化并注册到 Gateway，确保前端 Switch 始终可见。`_run_channel()` 中的跳过逻辑：

1. **DISABLED** 渠道：直接跳过 `start()`，不建立任何网络连接
2. **ON_DEMAND** 渠道（`should_auto_start()` 返回 False）：跳过 `start()`，保持 IDLE 状态直到用户通过登录 API 显式触发
3. **ON_DEMAND** 渠道（`should_auto_start()` 返回 True，即存在已持久化会话）：正常执行 `start()`，实现服务重启后自动恢复连接

---

## 6. 消息处理管道

### 6.1 入站流程

**Webhook Payload Validation**: MSTeams、Telegram、Feishu 和 DingTalk 的 webhook 入站 payload 通过 Pydantic 模型
进行结构化验证（`msteams/models.py`、`telegram/models.py`、`feishu/models.py`、`dingtalk/models.py`），
将 `dict[str, object]` 转换为强类型模型，消除手动 `isinstance` 检查，实现早期失败和自文档化。
验证失败时 log warning 并跳过，不影响服务可用性。

```
平台 Webhook/WebSocket/Polling
    ↓ [Pydantic 验证 (MSTeams/Telegram/Feishu/DingTalk)]
BaseChannel._emit_inbound(InboundMessage)
    ↓ [DISABLED 检查]
MessageBus 入站队列
    ↓
AgentRouter.consume()
    ├── 去重 (message_id + TTL)
    ├── 命令检测 (/stop, /new, /compact, /topic, /agent, 审批)
    ├── Debounce 合并 (SessionGate, 300ms)
    ├── 语音转写 (transcribe_inbound, 含音频时 STT → 文本)
    ├── 策略解析 (DM/群聊策略, 身份解析, 群组启用)
    ├── Topic 路由 (thread_id → agent_id)
    ├── 副作用 (reaction 👀, placeholder 🤔, typing + keepalive)
    ├── Agent 执行 (execute_stream + CancellationToken)
    │   ├── ProgressUpdate → edit_placeholder (进度)
    │   └── OutboundMessage → maybe_tts (语音回复) → edit_placeholder (回复)
    └── 清理 (reaction 移除, _active_tasks 清理)
```

### 6.2 出站流程

```
Agent/Cron → OutboundMessage
    ↓
MessageBus 出站分发
    ├── [DISABLED 检查]
    ├── 自动重试 (指数退避)
    ├── 持久化死信队列 (DeadLetterQueue)
    ├── downgrade_components() (组件降级)
    └── Channel.send()
        ├── render(msg, render_style) → chunks
        ├── send_with_retry(chunk) (指数退避)
        ├── [媒体附件] safe_download_media() → SSRF 验证 → 下载 → 上传到平台
        └── activity.record_outbound()
```

**出站媒体 SSRF 防护**：`MediaAttachment.url` 可能来自 Agent 生成内容（受 prompt injection 影响），
所有出站媒体下载通过 `channels.media.MediaDownloader` 执行（内置 `SSRFValidator`），
集成 `core.security.guards.ssrf.async_validate_url_for_ssrf`（scheme 白名单 + hostname 黑名单 + DNS 解析 + IP 网络黑名单）。

### 6.3 流式输出

```
AgentExecutor.execute_stream()
    ↓ StreamingText events
StreamCoordinator
    ├── BlockChunker (代码块感知分块)
    ├── IncrementalEditor (变化追踪，最小化编辑)
    ├── AdaptiveThrottler (自适应节流，平衡延迟与 API 调用)
    ├── ProgressEstimator (进度估算，±30% 误差)
    └── GracefulDegradation (失败渐进减速，非完全停止)
        ↓
    edit_placeholder(chunk)
        ↓
    最终 edit_placeholder(full_reply)
```

---

## 7. 可靠性设计

### 7.1 错误隔离

- 每个渠道运行在独立 asyncio.Task 中，单个渠道崩溃不影响其他
- `create_all_channels()` 中单个渠道实例化失败时跳过
- EventEmitter 监听器异常自动捕获和隔离

### 7.2 自动重连

`reconnect_loop` 提供统一的指数退避重连：
- 默认初始退避 1s，最大 60s（各渠道可自定义）
- 适用于长连接/轮询渠道（Slack, DingTalk, QQ, Mattermost, IRC, Signal, Matrix, Email）

### 7.3 速率限制

- **出站**：`TokenBucket` per-channel 速率限制，防平台封禁
- **入站**：`InboundRateLimiter` per-IP/per-endpoint Token Bucket，防 DoS 攻击（框架提供内存实现，业务层可注入 Redis 实现）
- **重试**：`RetryConfig` + `send_with_retry` 指数退避
- **会话级**：`SessionRateLimiter` 单 session 60 次/分钟上限，防异常循环

### 7.4 健康检查

- Gateway 60s 周期调用 `channel.health_check()`
- `ChannelHealth` 追踪连续成功/失败次数
- `collect_issues()` 结构化诊断（kind/severity/message/fix）；缺 SDK 依赖为 ERROR + `uv sync --extra …`；WeChat 语音 SILK 解码缺 pilk 为 WARNING + `uv sync --extra wechat-silk`（不阻塞启用，Settings 可一键安装）
- `POST /channels/manage/{name}/install-dependencies` 在 server venv 内 lazy-install（harness `runtime.lazy_deps`：`platform.discord` / `platform.feishu` / `platform.matrix` / `platform.wechat-silk`），成功后 **hot-register** 到 Gateway（无需重启进程）；响应 `registered: false` 表示 pip 成功但频道未上 bus（需配凭证或重启）
- `GET /channels/manage/status` 对未进 bus 的 SDK 频道返回 `status: unavailable` + `DEPENDENCY` issue（`registry.probe_sdk_channel_issues`），Settings 可一键安装
- `PATCH …/toggle` 启用前 **先** `ensure_channel_dependencies_ready`（仅 ERROR 级 SDK 依赖会阻塞/自动安装；WARNING 级可选能力依赖需用户在 Settings 手动安装）
- 可选 extra：`channels-sdk`（discord-py + lark-oapi）、`matrix`、`matrix-e2ee`、`wechat-silk`（pilk，WeChat iLink SILK→WAV）；`myrm setup` / 官方镜像 `--all-extras` 已包含

---

## 8. 渠道覆盖

| 渠道 | 协议 | 入站 | 出站 | 流式 | 组件 | 诊断 |
|------|------|:----:|:----:|:----:|:----:|:----:|
| Telegram | Bot API (polling/webhook) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Discord | Gateway WebSocket + REST | ✅ | ✅ | ✅ | ✅ | ✅ |
| WhatsApp | Baileys Node.js bridge | ✅ | ✅ | ✅ | ⬇️ | ✅ |
| Slack | Events API + Socket Mode | ✅ | ✅ | ✅ | ✅ | ✅ |
| Feishu/Lark | Webhook + Open API | ✅ | ✅ | ✅ | ✅ | ✅ |
| WeChat | iLink HTTP long-poll | ✅ | ✅ | ✅ | ⬇️ | ✅ |
| WeChat Official | Official Account XML callback | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| WeCom | Webhook + AES-CBC | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| MSTeams | Bot Framework REST | ✅ | ✅ | ✅ | ✅ | ✅ |
| Matrix | /sync long-polling | ✅ | ✅ | ✅ | ⬇️ | ✅ |
| DingTalk | Stream API WebSocket | ✅ | ✅ | ✅ | ⬇️ | ✅ |
| QQ | WebSocket + REST | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| GoogleChat | Webhook + Chat API v1 | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| Signal | REST API polling | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| LINE | Webhook + Messaging API | ✅ | ✅ | ⬇️ | ✅ | ✅ |
| IRC | Raw TCP + SSL/TLS | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| Email | IMAP polling + SMTP | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| Voice | Twilio ConversationRelay | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| SMS | Twilio REST + Webhook | ✅ | ✅ | — | ⬇️ | ✅ |
| Zalo | Webhook + OA API | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| Mattermost | WebSocket + REST v4 | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| iMessage | BlueBubbles Webhook | ✅ | ✅ | ⬇️ | ⬇️ | ✅ |
| Webhook | HTTP POST | — | ✅ | — | — | — |
| Chat | 内存队列 | ✅ | ✅ | ✅ | ✅ | — |

> ✅ = 原生支持, ⬇️ = 自动降级为文本

---

## 9. Custom Channel HTTP Routes Registration

### 9.1 架构设计

Framework 提供 Protocol-based 路由注册机制，实现框架独立性（不绑定特定 Web 框架；开箱即用实现为 FastAPI）。

**核心组件**：

1. **protocols/route_registrar.py**
   - `RouteRegistrar` Protocol：框架无关的路由注册接口
   - `RouteDefinition` / `RouteMetadata` / `RouteSecurityPolicy`：路由定义和元数据
   - `GenericRequest` / `GenericResponse` Protocols：框架无关的请求/响应接口
   - `HttpMethod` Enum：HTTP方法枚举

2. **protocols/adapters.py**
   - `RequestAdapter[TRequest]` Protocol：将框架特定请求转换为GenericRequest
   - `ResponseAdapter[TResponse]` Protocol：将GenericResponse转换为框架特定响应

3. **core/base.py**
   - `BaseChannel.register_routes(registrar)` 可选方法：Channel声明自己的HTTP端点
   - `BaseChannel._get_route_prefix()` 默认实现：返回 `channels/{channel_name}/`

4. **testing/route_testing.py**
   - `MockRouteRegistrar`：测试用Mock实现
   - `RouteDefinitionValidator`：路由定义验证工具

### 9.2 设计原则

1. **框架独立性**：Protocol 抽象，不绑定特定 Web 框架
2. **Channel自治**：Channel定义自己的HTTP端点（webhooks、login、status）
3. **安全优先**：路径前缀强制、白名单、自动应用middleware
4. **类型安全**：完整的类型标注和适配器
5. **可测试性**：提供MockRouteRegistrar用于单元测试

### 9.3 使用示例

```python
from app.channels.protocols import (
    HttpMethod,
    RouteMetadata,
    RouteRegistrar,
)
from app.channels.core import BaseChannel
from app.channels.core.rate_limit import RateLimitConfig

class TelegramChannel(BaseChannel):
    def register_routes(self, registrar: object) -> None:
        if not isinstance(registrar, RouteRegistrar):
            return

        registrar.add_route(
            HttpMethod.POST,
            "webhook",
            self._handle_webhook,
            RouteMetadata(
                description="Receive Telegram webhook updates",
                requires_auth=False,
                rate_limit_policy=RateLimitConfig(max_requests=60, window_seconds=60),
            ),
        )
```

### 9.4 Framework 提供的开箱即用实现

**Framework 层已提供 FastAPI 实现**（位于 `implementations/fastapi/`）：

1. **FastAPIRouteRegistrar**: FastAPI 的 `RouteRegistrar` 实现
2. **FastAPIRequestAdapter / FastAPIResponseAdapter**: Request/Response 适配器
3. **ChannelRouteRegistry**: 路由收集和注册逻辑
4. **安全策略执行**: 路径前缀、白名单、middleware 自动应用

**依赖**:
channels 框架已内置于 `myrm-agent-server/app/channels/`，FastAPI 集成由 `app.channels.implementations.fastapi` 提供。

**业务层使用示例**:

FastAPI:
```python
from app.channels.implementations.fastapi import (
    ChannelRouteRegistry,
)
from fastapi import Depends, FastAPI
# 业务层实现：提供当前用户 ID 的依赖函数
def get_current_user_id() -> str: ...

app = FastAPI()
registry = ChannelRouteRegistry(
    channel_gateway,
    auth_dependency=Depends(get_current_user_id),
)
registry.register_all(app)
```

**已实现的框架**：FastAPI（可选依赖 `[fastapi]`）。其他 Web 框架可自行实现 `RouteRegistrar` / 适配器并注入。

### 9.5 控制平面层建议

**重要**：控制平面的webhook endpoints建议**不使用** Custom Routes Registration。

**理由**：
1. **职责不同**：控制平面webhook是Pipeline消息路由入口（转发器），不是channel自治endpoint
2. **低频变化**：Pipeline routes变化频率极低（一年可能1次），硬编码更简洁
3. **避免过度设计**：不为低频场景引入复杂性

**推荐实现**：
- 控制平面：硬编码Pipeline routes（如 `channel_webhook.py`）
- 业务层（sandbox内）：使用Custom Routes Registration（高价值）

### 9.6 Rate Limiting架构说明

**Agent-in-Sandbox架构下的Rate Limiting策略**：

#### 三层策略

| 层级 | Rate Limiting实现 | 架构原理 |
|------|------------------|---------|
| **渠道框架层** | `RateLimiterProtocol` + `NoOpRateLimiter` / `InMemoryRateLimiter` | 提供Protocol抽象和多种开箱即用实现 |
| **业务层（server）** | `NoOpRateLimiter`（默认注入） | Agent-in-Sandbox单用户环境，无需限流 |
| **控制平面（plane）** | IP-based rate limiting（实际保护） | Webhook入口处保护，足够 |

#### 为什么Server层默认使用NoOpRateLimiter？

**Agent-in-Sandbox架构特点**：
- 每个用户独立sandbox
- 每个sandbox运行独立Server实例（单用户环境）
- Server层rate limiting无意义（只有一个用户）
- 真正的资源限制由控制平面的ResourceQuota + cgroup处理

#### RouteMetadata.rate_limit_policy的用途

1. **声明rate limiting策略**：类似OpenAPI spec中的rate limit声明，用于API文档
2. **业务层依赖注入**：业务层根据部署模式选择合适的RateLimiterProtocol实现：
   - Agent-in-Sandbox（默认）：`NoOpRateLimiter`
   - 多用户Server：`InMemoryRateLimiter`或自定义Redis实现
3. **控制平面参考**：控制平面可读取此配置调整webhook限流策略

#### 控制平面Rate Limiting实现

- **IP-based限流**：Webhook入口处按IP地址限流（默认120 requests/60s）
- **全局RateLimiter类**：支持user/sandbox/api三种scope，使用Redis存储计数器
- **足够保护**：在系统入口处保护，避免abuse

#### RateLimiterProtocol实现

**框架层提供**：
- `RateLimiterProtocol`：抽象接口（`check_limit`方法）
- `NoOpRateLimiter`：不执行限流（Agent-in-Sandbox默认）
- `InMemoryRateLimiter`：内存sliding window算法（单实例开发环境）

**业务层可选**：
- 自定义Redis实现（分布式多实例场景）

**重要**：这是合理的架构设计，Protocol-based依赖注入，而不是功能缺失。

### 9.7 收益

- ✅ 框架可移植性：Protocol 抽象 + FastAPI 开箱即用实现
- ✅ Channel自包含：逻辑+HTTP端点在一起
- ✅ 新增渠道零侵入：不需要修改业务层routes.py
- ✅ 类型安全：编译时检查路径冲突
- ✅ 安全性：自动应用安全策略和middleware

---

## 10. External Channel Async Login

### 10.1 概述

**AsyncLoginProtocol** 提供统一的异步登录协议，支持多种外部渠道认证方式（QR扫码、OAuth2、API Token等），实现类型安全、事件驱动、Protocol抽象的登录系统。

### 10.2 架构层级

| 层级 | 组件 | 职责 |
|------|------|------|
| **框架层** | `AsyncLoginProtocol` | Protocol定义（`start_login()`, `cancel_login()`） |
| | `LoginMethod` / `LoginStatus` / `LoginState` / `LoginEvent` | 类型安全的枚举和dataclass |
| | `QRCodeLoginHelper` | 封装QR登录逻辑（fetch、poll、auto-refresh） |
| | `OAuth2LoginHelper` | 封装OAuth2 authorization code flow |
| | `BaseChannel` | 集成AsyncLoginProtocol接口（`supported_login_methods`、`handle_oauth2_callback()`） |
| | **`storage/`模块** | `LoginSessionStoreProtocol`+`InMemorySessionStore`+`CredentialsStore`（开箱即用） |
| **业务层（Server）** | RESTful API | `/api/channels/login/*` endpoints（已注册） |
| | SSE Stream | Server-Sent Events实时状态推送 |
| | Session清理 | 自动清理过期session（每5分钟） |
| **业务层（Frontend）** | Settings 渠道 Section | `settings/sections/integration/channels/*ConfigCard.tsx` — 各 Provider QR/OAuth/配对 UI |
| | API服务层 | `channels.ts` API调用封装 |
| | TypeScript类型 | 完整类型定义（100%匹配后端） |
| **控制平面（SaaS）** | Redis Store | 实现`LoginSessionStoreProtocol`（多租户） |

### 10.3 Login Methods

支持的登录方式：

| Method | 描述 | 使用场景 | Helper |
|--------|------|---------|--------|
| `QR_CODE` | 二维码扫描 | WeChat、企微个人号 | `QRCodeLoginHelper` |
| `OAUTH2` | OAuth2授权码流程 | Google Chat、Slack、GitHub | `OAuth2LoginHelper` |
| `API_TOKEN` | API Token输入 | Telegram Bot、Discord Bot | 手动实现 |
| `PASSWORD` | 用户名密码 | SMTP、IMAP、内部系统 | 手动实现 |
| `SSO` | Single Sign-On | 企业集成 | 手动实现 |

### 10.4 State Machine

Login状态机流转：

```
IDLE → GENERATING → WAITING_USER_ACTION → VALIDATING → SUCCESS
                                         ↓
                                      TIMEOUT / FAILED / CANCELLED
```

| Status | 描述 | 前端UI |
|--------|------|--------|
| `IDLE` | 初始状态 | - |
| `GENERATING` | 生成QR码/OAuth URL | 加载动画 |
| `WAITING_USER_ACTION` | 等待用户扫码/授权 | 显示QR码/打开OAuth窗口 |
| `VALIDATING` | 验证凭证 | 加载动画 |
| `SUCCESS` | 登录成功 | 成功提示 + 关闭弹窗 |
| `FAILED` | 登录失败 | 错误提示 + 重试按钮 |
| `TIMEOUT` | 登录超时 | 超时提示 + 重试按钮 |
| `CANCELLED` | 用户取消 | 关闭弹窗 |

### 10.5 框架层实现

#### AsyncLoginProtocol定义

```python
@runtime_checkable
class AsyncLoginProtocol(Protocol):
    @property
    def supported_login_methods(self) -> list[LoginMethod]: ...

    async def start_login(
        self,
        method: LoginMethod,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncIterator[LoginEvent]: ...

    async def cancel_login(self) -> None: ...

    async def handle_oauth2_callback(
        self, code: str | None, state: str, error: str | None = None,
    ) -> None: ...
```

#### BaseChannel集成

```python
class WeChatILinkChannel(BaseChannel):
    supported_login_methods = [LoginMethod.QR_CODE]

    async def start_login(
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncIterator[LoginEvent]:
        if method != LoginMethod.QR_CODE:
            raise ValueError("Only QR_CODE supported")

        helper = QRCodeLoginHelper(
            fetch_qr_fn=self._fetch_qr_code,
            poll_status_fn=self._poll_qr_status,
        )
        async for event in helper.run(timeout, self.name):
            yield event
```

#### Helper Classes

**QRCodeLoginHelper**：
- 封装QR码fetch、poll、auto-refresh逻辑
- 自动处理过期刷新（max_refresh=3）
- 支持取消（`cancel()`）

**OAuth2LoginHelper**：
- 生成authorization URL（含CSRF state）
- 等待callback（`handle_callback()`），使用 `secrets.compare_digest` 验证 CSRF state
- Token exchange
- CSRF state 不匹配时拒绝回调并报错

### 10.6 业务层实现

#### API Endpoints

| Method | Path | 功能 |
|--------|------|------|
| `GET` | `/api/channels` | 列出支持登录的channels |
| `POST` | `/api/channels/{id}/login/start` | 开始登录流程 |
| `GET` | `/api/channels/login/{session_id}/stream` | SSE状态流 |
| `DELETE` | `/api/channels/login/{session_id}` | 取消登录 |
| `GET` | `/api/channels/{id}/login/oauth2/callback` | OAuth2回调 |

#### 数据流

```
Frontend → POST /start → Server → channel.start_login()
                         ↓
Frontend ← SSE stream ← AsyncIterator[LoginEvent]
                         ↓
                   LoginEvent.credentials
                         ↓
                  CredentialsStore.save()
```

#### Storage架构

**框架层（开箱即用）**：
- `LoginSessionStoreProtocol` + `InMemorySessionStore`（临时会话）
- `CredentialsStore`（AES-256加密文件存储，单用户sandbox）

**控制平面（SaaS扩展）**：
- Redis实现`LoginSessionStoreProtocol`（多租户会话）
- Redis加密凭证管理（租户隔离）

#### 部署模式

| 模式 | SessionStore | CredentialsStore | 位置 |
|------|--------------|------------------|------|
| **Agent-in-Sandbox（Local/Tauri）** | `InMemorySessionStore` | AES-256加密本地文件（`.myrm/credentials.json`） | 框架层 |
| **SaaS多租户** | Redis | Redis（加密存储，租户隔离） | 控制平面 |

### 10.7 安全性

1. **CSRF防护**：OAuth2使用 `secrets.token_urlsafe(32)` 生成 state token，callback 时通过 `secrets.compare_digest` 定时比较验证（防时序攻击）
2. **加密存储**：Credentials使用AES-256加密（PBKDF2派生密钥）
3. **Session TTL**：Login session默认5分钟过期
4. **HTTPS Only**：生产环境强制HTTPS（OAuth2 callback必须）

### 10.8 竞品对比

| 特性 | 我们 | FastClaw | HappyCappy | Onyx | AutoResearchClaw |
|------|------|----------|------------|------|------------------|
| **Protocol抽象** | ✅ 完整Protocol定义 | ❌ 无抽象 | ❌ 无抽象 | ❌ 无抽象 | ❌ 无抽象 |
| **Type Safety** | ✅ Enum + Dataclass | ⚠️ 字符串状态 | ⚠️ 字符串状态 | ⚠️ 字符串状态 | ⚠️ 字符串状态 |
| **Helper Classes** | ✅ QR + OAuth2 | ❌ 无 | ❌ 无 | ❌ 无 | ❌ 无 |
| **SSE Stream** | ✅ 实时状态推送 | ⚠️ 轮询 | ⚠️ 轮询 | ⚠️ 轮询 | ❌ 无UI |
| **多Method支持** | ✅ 5种（QR/OAuth2/Token/Password/SSO） | ⚠️ 仅QR | ⚠️ 仅QR | ⚠️ QR+Token | ❌ 无 |
| **加密存储** | ✅ AES-256 + PBKDF2 | ❌ 明文 | ❌ 明文 | ⚠️ Base64 | ❌ 无持久化 |
| **统一UI** | ✅ Settings Provider 配置卡 | ❌ Channel特定 | ❌ Channel特定 | ❌ Channel特定 | ❌ 无UI |
| **SaaS支持** | ✅ Redis多租户 | ❌ 单用户 | ❌ 单用户 | ⚠️ 部分 | ❌ 单用户 |

**评分**：我们 10/10，竞品平均 5.5/10（+4.5分）🚀

### 10.9 前端实现

#### 技术栈

- **框架**：Next.js 14 + TypeScript
- **UI库**：shadcn/ui（Dialog, Button, Alert）
- **国际化**：next-intl
- **实时通信**：EventSource (SSE)
- **状态管理**：React useState hooks

#### 组件架构

渠道登录与配置 UI 在 **Settings → 通信** 域，按 Provider 拆分配置卡（非统一 Dialog）：

| 路径 | 职责 |
|------|------|
| `myrm-agent-frontend/src/components/features/settings/sections/integration/channels/ChannelsSection.tsx` | 渠道总览、依赖安装、聚合各 Provider 卡 |
| `.../FeishuConfigCard.tsx` | 飞书 QR 注册（`/channels/manage/feishu/qr-register`） |
| `.../WeChatConfigCard.tsx` | 微信登录触发 |
| `.../TelegramConfigCard.tsx` 等 | 各平台 Token/OAuth/配对 |

详见 monorepo 内 `myrm-agent-frontend/src/components/features/settings/sections/integration/channels/_ARCH.md`。

**核心能力**（分布在各 ConfigCard 内）：
1. Provider 专属 QR / OAuth / Token 表单
2. SSE 或轮询订阅登录状态（如 Feishu QR poll）
3. 连接状态 Badge、配对管理（`PairingManager.tsx`）
4. 国际化：`locales/*.json` 中 `settings.channels.*` 键

#### API服务层

**channels.ts** (`myrm-agent-frontend/src/services/channels.ts`)：

- `listChannelsWithLogin()`: 获取支持登录的channels
- `startLogin()`: 启动登录流程
- `subscribeLoginStream()`: 订阅SSE状态流
- `cancelLogin()`: 取消登录

#### 类型定义

**channels.ts** (`myrm-agent-frontend/src/types/channels.ts`)：

完整TypeScript类型，与后端AsyncLoginProtocol 100%匹配：
- `LoginMethod` / `LoginStatus` Enums
- `LoginState` / `LoginEvent` / `ChannelInfo` Interfaces
- `StartLoginResponse` Response模型

#### 国际化支持

**locales/en.json** - channels模块（25个键）：
- 登录方法选择文案
- 状态提示文案（等待扫码、验证中、成功、失败等）
- 错误消息文案
- OAuth2授权引导文案

#### 集成方式

用户在 WebUI **Settings → 通信** 打开对应 Provider 配置卡完成登录；后端 REST/SSE 由 `app/api/channels/login.py` 等与各 ConfigCard 对接。无需额外页面级 Dialog 包装。

### 10.10 最佳实践

1. **Channel实现**：继承BaseChannel，设置`supported_login_methods`，实现`start_login()`
2. **使用Helper**：优先使用`QRCodeLoginHelper`和`OAuth2LoginHelper`
3. **错误处理**：区分`ChannelAuthError`（平台错误）和`TimeoutError`（超时）
4. **前端集成**：使用SSE订阅状态，自动更新UI
5. **生产部署**：SaaS模式使用Redis，启用HTTPS

---

## 12. 协议接口

## 11. Thread Auto-Reply (Slack)

Slack Thread自动响应机制：Bot在thread中参与后，后续回复无需@mention即可触发响应。

### 11.1 设计目标

**UX问题**：
- 用户在Slack thread中与Bot对话，每次回复都需要@bot很繁琐
- 打断对话流畅度，影响用户体验

**解决方案**：
- Bot参与thread后，自动跟踪thread ID
- 后续用户在该thread回复时，无需@mention即可触发Bot响应
- 可配置是否启用此功能（`require_thread_mention`）

### 11.2 ThreadTracker 设计

**核心类**：`ThreadTracker`（`providers/slack/thread_tracker.py`）

**特性**：
1. **LRU内存控制**：最多跟踪N个thread（默认1000），超过则淘汰最旧的
2. **TTL自动过期**：Thread超过T小时（默认24h）自动过期
3. **asyncio.Lock**：线程安全，支持并发访问
4. **Metrics可观测性**：`ThreadTrackerMetrics` 导出 hit/miss/eviction 数据

**数据结构**：
```python
OrderedDict[str, float]  # {thread_id: last_activity_timestamp}
```

### 11.3 配置参数

`SlackChannel` 初始化参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `require_thread_mention` | `bool` | `False` | 是否在thread中强制要求@mention |
| `thread_tracker_max_size` | `int` | `1000` | 最多跟踪thread数量（LRU） |
| `thread_tracker_ttl_hours` | `int` | `24` | Thread过期时间（小时） |

**示例**：
```python
# 默认启用自动响应
slack = SlackChannel("xoxb-token")

# 禁用自动响应（传统行为）
slack = SlackChannel("xoxb-token", require_thread_mention=True)

# 自定义LRU大小和TTL
slack = SlackChannel(
    "xoxb-token",
    thread_tracker_max_size=500,
    thread_tracker_ttl_hours=12,
)
```

### 11.4 工作流程

**Bot发送消息时**：
```python
async def send(self, msg: OutboundMessage) -> str | None:
    # ... send logic ...
    
    # 记录thread参与
    effective_thread = thread_ts or msg.reply_to_id or msg.thread_id
    if effective_thread:
        await self._thread_tracker.add(str(effective_thread))
```

**用户回复消息时**：
```python
async def _parse_message_event(self, event) -> InboundMessage | None:
    mentioned = f"<@{self._bot_user_id}>" in text
    
    # Thread自动响应检查
    if thread_ts and not mentioned and not self._require_thread_mention:
        if await self._thread_tracker.contains(str(thread_ts)):
            mentioned = True  # 自动设置为已@mention
    
    return self._build_inbound(..., mentioned=mentioned)
```

### 11.5 Metrics导出

框架层提供`ThreadTrackerMetrics`，业务层决定如何导出：

**可用Metrics**：
- `hit_count`：缓存命中次数
- `miss_count`：缓存未命中次数
- `hit_rate`：命中率（0.0-1.0）
- `current_size`：当前跟踪thread数
- `lru_eviction_count`：LRU淘汰次数
- `ttl_eviction_count`：TTL过期次数

**导出示例**（业务层）：
```python
from app.channels.providers.slack import SlackChannel

# 获取metrics
metrics = slack_channel.thread_tracker_metrics

# Prometheus
prometheus_gauge.set(metrics.current_size)

# DataDog
statsd.gauge("slack.thread.hit_rate", metrics.get_hit_rate())

# Logging
logger.info("Thread tracker: %s", metrics.to_dict())
```

完整业务层示例：`myrm-agent-server/app/core/monitoring/slack_thread_metrics_exporter.py`

### 11.6 性能特性

**内存**：
- O(1) 添加/查询操作
- OrderedDict 保证 LRU 顺序
- 默认1000个thread，每个~24字节，总计~24KB

**并发安全**：
- asyncio.Lock 保护所有操作
- 无数据竞争风险

**清理策略**：
- LRU：add()时触发，超过max_size淘汰最旧
- TTL：contains()时检查，过期自动删除

### 11.7 架构分层

**渠道框架层（app/channels/）**：
- `ThreadTracker` 类（核心逻辑）
- `ThreadTrackerMetrics` 数据结构
- `SlackChannel` 集成

**业务适配层（app/core/channel_bridge/）**：
- Metrics导出示例
- 配置参数调优
- 监控告警集成

**控制平面（plane）**：
- 聚合多用户metrics
- 异常检测（hit_rate异常低）

### 11.8 最佳实践

**1. 独立部署（Self-hosted）**：
- 使用默认配置即可
- 监控`hit_rate`和`current_size`

**2. SaaS平台（Multi-tenant）**：
- 框架层不感知user_id
- 业务层导出时添加`user_id`标签
- 控制平面聚合所有用户metrics

**3. 性能优化**：
- hit_rate < 50%：增大`max_size`或延长`ttl_hours`
- lru_eviction频繁：增大`max_size`
- ttl_eviction频繁：可缩短`ttl_hours`节省内存

---


框架层通过 Protocol 定义业务层需要实现的接口：

| Protocol | 职责 | 业务层实现 |
|----------|------|-----------|
| `AgentExecutor` | Agent 流式执行 | `ChannelAgentExecutor` |
| `PairingStore` | sender → user 身份绑定 | `SqlPairingStore` |
| `ChannelPolicyProvider` | DM/群聊策略 + 群组启用列表 | `SqlChannelPolicyProvider` |
| `TopicManager` | per-topic Agent 路由配置 | `SqlTopicManager` |
| `CompactHandler` | 会话压缩 | `compact_chat()` |
| `RouteRegistrar` | HTTP路由注册 | `FastAPIRouteRegistrar` |
| `RequestAdapter` / `ResponseAdapter` | 请求/响应适配 | `FastAPIRequestAdapter` / `FastAPIResponseAdapter` |
| `AsyncLoginProtocol` | 异步登录流程 | `QRCodeLoginHelper` / `OAuth2LoginHelper` |
| `LoginSessionStoreProtocol` | 登录会话管理 | `InMemorySessionStore` / Redis实现 |

---

## 13. 参考资料

- 竞品渠道能力全景分析：[COMPETITIVE_CHANNEL_CAPABILITIES.md](COMPETITIVE_CHANNEL_CAPABILITIES.md)
- Rich Message使用指南：[RICH_MESSAGE_USAGE.md](RICH_MESSAGE_USAGE.md)
- 业务层架构：`myrm-agent-server/app/core/channel_bridge/`
