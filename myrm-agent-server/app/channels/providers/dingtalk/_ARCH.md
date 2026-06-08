# channels/providers/dingtalk/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | DingTalk channel package — re-exports DingTalkChannel for registry. | ✅ |
| `api.py` | 模块 | DingTalk OpenAPI client. Encapsulates token management, message sending (DM/group), media upload/download, and AI Card streaming for DingTalkChannel. """ | ✅ |
| `channel.py` | 模块 | DingTalk robot channel. Stream API WebSocket for inbound, OpenAPI for outbound. Supports DM/group routing, media upload with fallback, AI Card streaming, and st | ✅ |
| `helpers.py` | 模块 | app.channels.providers.dingtalk.helpers — Pure helper functions for DingTalk channel. """ | ✅ |
| `models.py` | 模块 | Pydantic models for DingTalk robot callback payloads. """ | ✅ |
