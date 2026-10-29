# channels/providers/mattermost/

## 架构概述

Mattermost 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Mattermost channel provider — WebSocket inbound + REST API v4 outbound. | ✅ |
| `api.py` | 模块 | app.channels.providers.mattermost.api — Mattermost REST API v4 client with Bot Access Token auth. `create_post` and `update_post` are the only paths that carry text, and both pass it through `neutralize_broadcast_mentions()`, which puts a zero-width space after the `@` of `@channel`, `@all` and `@here` so a reply, placeholder or progress edit never notifies the whole channel. | ✅ |
| `channel.py` | 模块 | app.channels.providers.mattermost.channel — credentials, lifecycle, REST API v4 outbound, groups and diagnostics (reaction emojis are sent as short names, via `providers/_emoji_shortnames.py`); composes `MattermostInboundMixin`. | ✅ |
| `inbound.py` | 模块 | `MattermostInboundMixin`: WebSocket session (`_ws_connect`), `posted` / `reaction_added` parsing, mention handling and inbound media. | ✅ |
