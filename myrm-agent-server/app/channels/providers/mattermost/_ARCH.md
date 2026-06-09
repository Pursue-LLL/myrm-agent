# channels/providers/mattermost/

## 架构概述

Mattermost 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Mattermost channel provider — WebSocket inbound + REST API v4 outbound. | ✅ |
| `api.py` | 模块 | app.channels.providers.mattermost.api — Mattermost REST API v4 client with Bot Access Token auth. | ✅ |
| `channel.py` | 模块 | app.channels.providers.mattermost.channel — Mattermost WebSocket inbound + REST API v4 outbound. | ✅ |
