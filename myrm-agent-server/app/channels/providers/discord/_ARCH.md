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

## 测试（`tests/channels/providers/discord/`）

| 文件 | 职责 |
|------|------|
| `test_discord_channel.py` | Gateway/forum/lifecycle、edit/delete、voice 配置 |
| `test_discord_embed_and_contract.py` | Embed/View 纯函数、`ChannelTestBase` 契约合规 |
| `voice/test_*.py` | Discord 语音子模块 |
