# channels/providers/wecom/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WeCom (Enterprise WeChat) channel providers. | ✅ |
| `aibot_channel.py` | 模块 | WeCom AI Bot channel: WebSocket long-lived connection, no public IP required, native streaming replies. Supports message/event callbacks, welcome messages, temp | ✅ |
| `channel.py` | 模块 | WeCom self-built app channel: AES encrypted callbacks, multimedia send/receive, @mention detection, OAuth token management. """ | ✅ |
| `crypto.py` | 模块 | WeCom message encryption/decryption. Implements AES-CBC + PKCS7 padding + SHA1 signature verification for Webhook callback message security. """ | ✅ |
