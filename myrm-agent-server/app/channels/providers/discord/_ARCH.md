# channels/providers/discord/

## 架构概述

Discord 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Discord channel provider. | ✅ |
| `channel.py` | 模块 | Discord channel implementation with Forum channel support: credentials, capabilities, gateway lifecycle (a stop leaves voice within a bound; the voice manager lives as long as the gateway client) and health probe; builds the client with `allowed_mentions` that keep user and reply pings but never `@everyone`, `@here` or role pings; composes the three mixins below. | ✅ |
| `config.py` | 模块 | Discord channel configuration. | ✅ |
| `helpers.py` | 模块 | Pure-function helpers for the Discord channel. Converts framework message objects to Discord native objects; forum detection, thread titles and native reply targets. | ✅ |
| `inbound.py` | 模块 | `DiscordInboundMixin`: gateway message / reaction / interaction parsing, reply context, media extraction, auto-threading and history fetch. | ✅ |
| `outbound.py` | 模块 | `DiscordOutboundMixin`: REST sending with `render()` multi-chunk delivery through `deliver_chunks`, forum threads (tags via `ForumChannel.flags.require_tag`), placeholder / edit / delete / react / typing. | ✅ |
| `voice_control.py` | 模块 | `DiscordVoiceMixin`: opus loading, `VoiceManager` wiring (one manager per gateway client, kept across READY events), join / leave / play_audio, voice-input emission and the `/voice` slash command. | ✅ |

## Reply Threading / Quote 保真

Discord provider 完整实现了 `ReplyContext` 协议（与其他 7 个渠道一致）：

**Inbound**:
- `_parse_reply_context()`: 解析 `message.reference.resolved`（discord.py 的真实 API）为结构化 `ReplyContext`，支持 text + embed content + attachments。`resolved` 为 `DeletedReferencedMessage` 或 `None` 时回退到 ID-only minimal context。
- `_resolve_mentioned()`: 群组中 `@bot` 或引用 bot 消息均视为 mentioned（返回 `(mentioned, explicit_mention)`，与 Telegram `inbound_message.py` 的 `_parse_message_model` 同一模式），并在显式提及群聊中注入 `explicit_mention="1"` 元数据。
- `_strip_bot_mention_text()`: 群聊入站消息标准化清洗，剥离 `<@!BOT_ID>` raw mention 前缀，保持入站文本前缀稳定以利于 Prompt Cache 布局一致。
- `is_group = message.guild is not None`: 正确区分群组和 DM。

**Outbound**:
- `send()`: 当 `reply_to_id` 存在时，首个分片带 `reference=reply_reference(channel, reply_to_id)`（`MessageReference(message_id, channel_id, fail_if_not_exists=False)`）实现原生 Discord reply 链，引用消息被删除时仍能正常发送；`reply_to_id` 不是 snowflake 或频道无 id 时降级为普通消息。

## Health Check (Zombie WS 检测)

`health_check()` 使用 REST API `fetch_user(user.id)` 探针检测连接可靠性。discord.py 的 WS 在 NAT/代理卡死场景下可能假死（socket 未收到 RST），`Client.start()` 永远挂住。REST probe 不依赖 WS 状态，能独立验证网络连通性，配合 Gateway `_health_loop` 实现自动检测和重启。

## Stop（语音离开限时）

`stop()` 的顺序是：离开语音、`client.close()`、取消网关会话、置 STOPPED。会话放最后，因为 discord.py 的语音离开要等网关事件确认。这个等待每个语音连接最多 30 秒，并且在等待期间吞掉取消，所以网关给整个 `stop()` 的 10 秒上限（`stop_channel`）拦不住它。`_leave_voice` 把离开放进单独的任务，最多等 `_VOICE_LEAVE_TIMEOUT`（4 秒）：

- 超时，或调用方被取消，取消该任务但不等它；
- 超时后，对 `client.voice_clients` 里还留着的连接调 `cleanup()` 摘除，随后 `client.close()` 不会为它们再等一轮确认；
- `VoiceManager.leave_all()` 让各公会并发离开，被放弃的离开在每个公会上都已经在进行；一个公会卡住或出错都不挡其余公会，出错记 WARNING；
- 不在 `stop_channel` 里通用地放弃 `stop()`：渠道重启复用同一个实例，被放弃的 `stop()` 之后若继续跑，会把新启动的客户端关掉。

## 语音管理器的生命周期

`VoiceManager` 与网关客户端同寿命，不跟 `on_ready` 走：

- 同一个客户端上 `on_ready` 会触发多次：会话被 Discord 判为不可恢复时，discord.py 在同一个 `Client` 上重新 IDENTIFY，新的 READY 先清空它自己的 `voice_clients` 再派发 `on_ready`。`_init_voice_manager` 已有管理器就沿用，仍在通话的会话、接收器和跟随循环不丢，`stop()` 的 `leave_all()` 也找得到它们；
- `_start_gateway` 新建客户端时丢掉上一个客户端留下的管理器：被取消的 `stop()` 没走到 `_voice_manager = None`，而它的 `leave_all()` 已经销毁了跟随循环，重启后的新客户端不能沿用；
- `VoiceManager.join` 遇到「已登记、连接却已结束」的公会（没有事件把它从登记表里摘掉，例如网关断开时的本地离开）时，先摘掉登记并 `_release` 旧会话，再建立新连接：旧会话的监听循环不能活过它的连接，否则它的静默超时会按公会号离开，结束新会话；
- 语音离开上限 `_VOICE_LEAVE_TIMEOUT` 必须小于网关的停止上限 `_STOP_TIMEOUT`，`test_discord_stop_voice.py` 钉住这个关系。

## 测试（`tests/channels/providers/discord/`）

| 文件 | 职责 |
|------|------|
| `test_discord_channel.py` | Gateway/forum/lifecycle（含网关任务已失败时的停止）、edit/delete、原生 reply 引用（首分片携带 message_id + channel_id）、voice 配置、health_check REST probe |
| `test_discord_stop_voice.py` | 停止时的语音离开：真实 `VoiceConnectionState`（只替换网络），覆盖网关永远不确认、某个公会在等待之前就卡住、网关正常确认、`stop()` 在等待中被取消四种情形；前两种在限时内返回，所有公会的套接字都已释放；另钉住语音离开上限小于网关停止上限 |
| `test_discord_voice_manager_lifetime.py` | 语音管理器的生命周期：第二次 READY 沿用管理器及其会话（`stop()` 仍断开该会话一次）；被取消的 `stop()` 之后重启得到新管理器 |
| `test_discord_allowed_mentions.py` | 网关客户端的提及策略：discord.py 实际发出的 `allowed_mentions` 载荷只放行用户与回复引用，不含 everyone、角色 |
| `test_discord_reply_context.py` | `_parse_reply_context` / `_resolve_mentioned` 单元测试（reference.resolved API 验证） |
| `test_discord_embed_and_contract.py` | Embed/View 纯函数、`ChannelTestBase` 契约合规 |
| `test_discord_deduplication.py` | Discord 消息去重单元测试 |
| `test_discord_splitter_integration.py` | Splitter 对 Discord 消息拆分约束的集成测试 |
| `voice/test_*.py` | Discord 语音子模块（`voice/test_leave_all.py`：各公会并发离开，一个公会卡住或出错不挡其余；`voice/test_join_stale_state.py`：对连接已结束的会话再次加入时先释放它，旧会话的静默超时不结束新会话，连接失败不留下已释放的登记） |
