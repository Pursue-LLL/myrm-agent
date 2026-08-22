# channels/providers/onebot/

## 架构概述

OneBot 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | OneBot v11 Channel Provider. | ✅ |
| `channel.py` | 模块 | OneBot v11 channel adapter. WebSocket reverse server for NapCatQQ/go-cqhttp. Outbound `send()` uses `render()` multi-chunk delivery (Item 46). | ✅ |
| `helpers.py` | 模块 | Pure-function helpers for the OneBot channel. Handles bidirectional conversion between OneBot v11 message segments and framework message objects. | ✅ |
