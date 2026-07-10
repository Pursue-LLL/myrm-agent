# channels/providers/whatsapp/

## 架构概述

WhatsApp 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WhatsApp channel provider via Baileys multi-device bridge. | ✅ |
| `bridge.py` | 模块 | Bridge process management. WhatsAppChannel inherits spawn/read/write/kill via Mixin; channel.py focuses on business logic (event dispatch, messaging). | ✅ |
| `channel.py` | 模块 | WhatsApp integration: inbound bridge->_handle_inbound->_emit_inbound, outbound bridge stdin "send". | ✅ |
| `format_converter.py` | 模块 | WhatsApp format conversion. Protects code blocks/inline code, converts formatting markers, restores protected content. | ✅ |
| `helpers.py` | 模块 | WhatsApp JID normalization, mention detection, self-chat detection, and path constants. Shared by channel.py and bridge.py. | ✅ |
| `bridge/` | 子目录 | Node.js Baileys bridge 子进程（`whatsapp-bridge.js`）及其 npm 依赖。见 [`bridge/_ARCH.md`](bridge/_ARCH.md)。 | — |
