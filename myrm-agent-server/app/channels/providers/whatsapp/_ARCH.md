# channels/providers/whatsapp/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WhatsApp channel provider via Baileys multi-device bridge. | ✅ |
| `bridge.py` | 模块 | Bridge process management. WhatsAppChannel inherits spawn/read/write/kill via Mixin; channel.py focuses on business logic (event dispatch, messaging). """ | ✅ |
| `channel.py` | 模块 | WhatsApp integration: inbound bridge->_handle_inbound->_emit_inbound, outbound bridge stdin "send". """ | ✅ |
| `format_converter.py` | 模块 | WhatsApp format conversion. Protects code blocks/inline code, converts formatting markers, restores protected content. """ | ✅ |
| `helpers.py` | 模块 | WhatsApp JID normalization, mention detection, self-chat detection, and path constants. Shared by channel.py and bridge.py. """ | ✅ |
