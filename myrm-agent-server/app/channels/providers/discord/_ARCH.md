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
| `inbound.py` | 模块 | `DiscordInboundMixin`: gateway message / reaction / interaction parsing, reply context, media extraction, auto-threading and history fetch. A message names its author by `sender_id` only; the router's resolvers assign `user_id`. | ✅ |
| `outbound.py` | 模块 | `DiscordOutboundMixin`: REST sending with `render()` multi-chunk delivery through `deliver_chunks`, forum threads (tags via `ForumChannel.flags.require_tag`), placeholder / edit / delete / react / typing. | ✅ |
| `voice_control.py` | 模块 | `DiscordVoiceMixin`: opus loading, `VoiceManager` wiring (one manager per gateway client, kept across READY events), join / leave / play_audio, voice-input emission (a speaker is checked against the access policy before their audio is transcribed) and the `/voice` slash command, whose caller is checked against the access policy first. | ✅ |

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
- `VoiceManager.join` 遇到「已登记、VoiceClient 未连接」的公会时，看 discord.py 是否还持有该 VoiceClient（`channel.guild.voice_client`）：还持有，说明它在重连，本次加入返回 False、会话原样保留（释放它会留下一个无人管理却仍在频道里的连接：`leave` 找不到状态，`join` 被 `Already connected` 拒绝）；已被摘掉（没有事件把状态从登记表里摘掉，例如网关断开时的本地离开），先摘掉登记并 `_release` 旧会话，再建立新连接：旧会话的监听循环不能活过它的连接，否则它的静默超时会按公会号离开，结束新会话；
- 语音离开上限 `_VOICE_LEAVE_TIMEOUT` 必须小于网关的停止上限 `_STOP_TIMEOUT`，`test_discord_stop_voice.py` 钉住这个关系。

## 发送者身份与准入

**身份。** 适配器的每一条入站（文本消息、按钮点击、历史回填、语音转写）都只填 `sender_id`，不填 `user_id`。`user_id` 是路由器的解析器按 DM 策略与配对「分配」的身份；解析器只采信控制面转发（带 `trusted_inbound: control_plane`）自带的 `user_id`，其余消息带着的一律忽略（`resolve_dm_user` 与私聊准入判定都如此），适配器无法替自己的发送者指定身份。适配器不填，私聊与语音转写就由解析器决定它们是谁：

- 私聊与语音转写按 DM 策略与配对解析（默认 ALLOWLIST，只有已配对者进入回合；PAIRING 策略下未知发送者得到待审配对）。所有者需要有效的管理员配对（设置里的配对表单可选角色）才被识别为所有者；已配对成员以 `paired_member_` 身份运行并被栅栏；
- 机器人发来的私聊也受 `BotLoopGuard` 限流；
- 群聊路径只用 `sender_id`，不受影响。

**语音说话人。** `VoiceManager._listen_loop` 在 `allowed_users` 过滤之后、转写之前，对每段话问一次 `speaker_gate`（`DiscordVoiceMixin._voice_speaker_admitted`）：用 `_voice_message` 构造一条与转写文本进入入站管道时完全同形的私聊消息（发送者为说话人，`chat_id` 为会话的文本频道），交给 `BaseChannel.is_sender_admitted`。被拒绝的人，音频不进入语音转写（不产生转写调用），也不延长会话的静默计时；每个会话中每个说话人第一次被拒记一条 WARNING；判定未接线则不转写任何人。`allowed_users` 为空仍表示「听所有人」，但听到之后要过这一关。判定与转写文本之后的解析依据同一套 DM 策略与配对（`check_sender_admitted` 与 `resolve_dm_user` 互为镜像）；每日额度与机器人环路防护只在解析器里判定，所以被放行并转写的话，仍可能因额度用尽而没有回合。

**`/voice` 命令。** `/voice join|leave|status` 是 Discord 交互，不经过入站管道，所以不会像文本消息那样被访问策略筛一遍。命令先 `defer(ephemeral=True)` 应答（Discord 要求 3 秒内应答，判定要读策略存储），再问 `_voice_command_admitted`：用调用者构造一条与文本消息同形的入站消息（发送者为调用者 id，`chat_id` 为发出命令的频道，公会内为群聊，不带 `user_id` 与提及），交给 `BaseChannel.is_sender_admitted`，由路由器的发送者准入判定回答：公会里，所有者（有效的管理员配对）与已启用群聊的成员放行，群聊策略为 DISABLED 或群聊未启用则拒绝（命令不带显式提及，访客模式不放行）；私聊里按 DM 策略与配对判定，陌生人被拒，已配对者之后以「只能在服务器里使用」回应。所有回复都走 followup、仅调用者可见。拒绝时回「You are not allowed to use this command. Ask the bot owner to give you access.」，记一条带用户、频道、公会的 WARNING，不加入、不离开、不回报状态；判定未接线或查询出错同样拒绝。

**两条口径的差别。** `/voice` 是对机器人所在频道做的动作，按群聊口径（所有者在任何频道、已启用群聊的成员）；说话是对机器人说话，按私聊口径（已配对者）。所以已启用群聊里未配对的成员可以让机器人加入语音，但他的话不会被转写；要让他被听到，需为他建立配对。

## 测试（`tests/channels/providers/discord/`）

| 文件 | 职责 |
|------|------|
| `test_discord_channel.py` | Gateway/forum/lifecycle（含网关任务已失败时的停止）、edit/delete、原生 reply 引用（首分片携带 message_id + channel_id）、voice 配置、health_check REST probe |
| `test_discord_stop_voice.py` | 停止时的语音离开：真实 `VoiceConnectionState`（只替换网络），覆盖网关永远不确认、某个公会在等待之前就卡住、网关正常确认、`stop()` 在等待中被取消四种情形；前两种在限时内返回，所有公会的套接字都已释放；另钉住语音离开上限小于网关停止上限 |
| `test_discord_voice_manager_lifetime.py` | 语音管理器的生命周期：第二次 READY 沿用管理器及其会话（`stop()` 仍断开该会话一次）；被取消的 `stop()` 之后重启得到新管理器 |
| `test_discord_voice_command_admission.py` | `/voice` 命令的发送者准入：命令先于判定应答（defer）、所有回复走 followup；被拒绝的调用者三个子命令都只收到仅自己可见的拒绝回复，不加入、不离开、不回报状态；判定未接线时拒绝所有人；放行的调用者三个子命令照常；判定收到的消息字段（发送者、频道、群聊，不带 `user_id`）；拒绝记带频道的 WARNING |
| `test_discord_sender_identity.py` | 适配器接真实总线、路由器与解析器（存储为内存替身，配对替身按 `SqlPairingStore.resolve` 的规则按渠道名与发送者查询并给出身份：管理员为 `sandbox`，其余为 `paired_member_{渠道}_{发送者}`）：陌生人的私聊、按钮点击与语音转写不产生回合；已配对成员以 `paired_member_` 身份被栅栏；所有者以所有者身份运行；未配对的说话人不被转写，已配对成员与所有者被转写；`/voice` 在已启用频道对未配对成员放行、在未启用频道对陌生人拒绝、对所有者放行、私聊里对陌生人拒绝；历史回填不带 `user_id` |
| `gateway_testkit.py` | 构造不联网的 `DiscordChannel` 与网关客户端替身（生命周期、语音命令、身份三组测试共用） |
| `test_discord_allowed_mentions.py` | 网关客户端的提及策略：discord.py 实际发出的 `allowed_mentions` 载荷只放行用户与回复引用，不含 everyone、角色 |
| `test_discord_reply_context.py` | `_parse_reply_context` / `_resolve_mentioned` 单元测试（reference.resolved API 验证） |
| `test_discord_embed_and_contract.py` | Embed/View 纯函数、`ChannelTestBase` 契约合规 |
| `test_discord_deduplication.py` | Discord 消息去重单元测试 |
| `test_discord_splitter_integration.py` | Splitter 对 Discord 消息拆分约束的集成测试 |
| `voice/test_*.py` | Discord 语音子模块（`voice/test_leave_all.py`：各公会并发离开，一个公会卡住或出错不挡其余；`voice/test_input_pipeline.py`：语音输入门控（转写幻觉过滤、回声与打断、唤醒词与唤醒窗口、显示名、播放登记）；`voice/test_join_stale_state.py`：再次加入时先释放 discord.py 已摘掉的会话，重连中的会话原样保留，旧会话的静默超时不结束新会话，连接失败不留下已释放的登记；`voice/test_speaker_gate.py`：说话人闸门（放行才转写、被拒绝的音频不进转写且不延长会话、未接线不转写任何人、先过 `allowed_users` 再问闸门、每段话都重新判定、每说话人首次被拒只记一次）；`voice/listen_testkit.py`：把给定的话送过一轮监听循环、替身掉转写入口） |
