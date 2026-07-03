# channels/providers/discord/

## 架构概述

Discord 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Discord channel provider. | ✅ |
| `channel.py` | 模块 | Discord channel implementation with Forum channel support. | ✅ |
| `config.py` | 模块 | Discord channel configuration. | ✅ |
| `helpers.py` | 模块 | Pure-function helpers for the Discord channel. Converts framework message objects to Discord native objects. | ✅ |

## Reply Threading / Quote 保真

Discord provider 完整实现了 `ReplyContext` 协议（与其他 7 个渠道一致）：

**Inbound**:
- `_parse_reply_context()`: 解析 `message.reference.resolved`（discord.py 的真实 API）为结构化 `ReplyContext`，支持 text + embed content + attachments。`resolved` 为 `DeletedReferencedMessage` 或 `None` 时回退到 ID-only minimal context。
- `_resolve_mentioned()`: 群组中 `@bot` 或引用 bot 消息均视为 mentioned（与 Telegram `inbound.py:356-358` 同一模式）。
- `is_group = message.guild is not None`: 正确区分群组和 DM。

**Outbound**:
- `send()`: 当 `reply_to_id` 存在时传 `reference=discord.MessageReference(fail_if_not_exists=False)` 实现原生 Discord reply 链，引用消息被删除时仍能正常发送。

## Health Check (Zombie WS 检测)

`health_check()` 使用 REST API `fetch_user(user.id)` 探针检测连接可靠性。discord.py 的 WS 在 NAT/代理卡死场景下可能假死（socket 未收到 RST），`Client.start()` 永远挂住。REST probe 不依赖 WS 状态，能独立验证网络连通性，配合 Gateway `_health_loop` 实现自动检测和重启。

## 测试（`tests/channels/providers/discord/`）

| 文件 | 职责 |
|------|------|
| `test_discord_channel.py` | Gateway/forum/lifecycle、edit/delete、voice 配置、health_check REST probe |
| `test_discord_reply_context.py` | `_parse_reply_context` / `_resolve_mentioned` 单元测试（reference.resolved API 验证） |
| `test_discord_embed_and_contract.py` | Embed/View 纯函数、`ChannelTestBase` 契约合规 |
| `voice/test_*.py` | Discord 语音子模块 |
