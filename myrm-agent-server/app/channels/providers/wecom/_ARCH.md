# channels/providers/wecom/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 见源码 | — |
| `aibot_channel.py` | 模块 | WeCom AI Bot channel: WebSocket long-lived connection, no public IP required, | ✅ |
| `channel.py` | 模块 | WeCom self-built app channel: AES encrypted callbacks, multimedia send/receive, | ✅ |
| `crypto.py` | 模块 | WeCom message encryption/decryption. Implements AES-CBC + PKCS7 padding + SHA1 | ✅ |
