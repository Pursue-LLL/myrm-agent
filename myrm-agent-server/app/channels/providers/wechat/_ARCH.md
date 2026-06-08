# channels/providers/wechat/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WeChat channel providers. | ✅ |
| `ilink_channel.py` | 模块 | WeChat personal account channel implementation. Sends/receives messages via iLink Bot protocol. Supports text, image, voice (STT), file, video, and typing indic | ✅ |
| `official_channel.py` | 模块 | WeChat Official Account channel implementation. Supports passive replies, customer service messages, rich-media (news) messages, and media send/receive. """ | ✅ |
