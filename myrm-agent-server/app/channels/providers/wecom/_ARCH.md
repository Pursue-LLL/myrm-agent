# channels/providers/wecom/

## 架构概述

企业微信 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WeCom (Enterprise WeChat) channel providers. | ✅ |
| `aibot_channel.py` | 模块 | WeCom AI Bot channel: WebSocket long-lived connection, no public IP required, native streaming replies. Supports message/event callbacks, welcome messages, temp | ✅ |
| `aibot_inbound.py` | 模块 | WeCom AI Bot inbound mixin. WebSocket session (subscribe + heartbeat + frame loop), callback dispatch and inbound message / quote parsing. | ✅ |
| `channel.py` | 模块 | WeCom self-built app channel: AES encrypted callbacks, multimedia send/receive, @mention detection, OAuth token management. | ✅ |
| `constants.py` | 模块 | WeCom self-built application API constants (base URL, HTTP timeouts, token refresh buffer) shared by the channel and its inbound mixin. | ✅ |
| `crypto.py` | 模块 | WeCom message encryption/decryption. Implements AES-CBC + PKCS7 padding + SHA1 signature verification for Webhook callback message security. | ✅ |
| `inbound.py` | 模块 | WeCom self-built app inbound mixin. Webhook signature verification, encrypted XML callback handling and inbound media download. | ✅ |
| `user_resolver.py` | 模块 | WeCom user resolver using contact API with LRU+TTL caching. Resolves sender display names for group chat context. | ✅ |
