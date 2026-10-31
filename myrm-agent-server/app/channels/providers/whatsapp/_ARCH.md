# channels/providers/whatsapp/

## 架构概述

WhatsApp 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WhatsApp channel provider via Baileys multi-device bridge. | ✅ |
| `bridge.py` | 模块 | Bridge process management. WhatsAppChannel inherits spawn/read/write/kill via Mixin; channel.py and inbound.py focus on business logic (messaging, event dispatch). The npm install and the bridge are Node processes that inherit none of the host's TLS policy, so both get `NODE_USE_SYSTEM_CA=1` through `with_node_system_ca` while the enterprise network compatibility setting is on (the proxy variables the bridge drops are removed first). | ✅ |
| `channel.py` | 模块 | WhatsApp integration core: lifecycle, outbound bridge stdin commands and media/group/typing/reaction requests; composes `WhatsAppInboundMixin`, `WhatsAppLoginMixin` and `BridgeProcessMixin`. | ✅ |
| `format_converter.py` | 模块 | WhatsApp format conversion. Protects code blocks/inline code, converts formatting markers, restores protected content. | ✅ |
| `helpers.py` | 模块 | WhatsApp JID normalization, mention detection, self-chat detection, message-key and quote parsing, and path constants. Shared by channel.py and bridge.py. | ✅ |
| `inbound.py` | 模块 | `WhatsAppInboundMixin`: bridge event dispatch, connection state, group sync, and message / reaction parsing into `InboundMessage`. | ✅ |
| `login.py` | 模块 | `WhatsAppLoginMixin`: QR-code pairing events streamed to the frontend as `LoginEvent` (AsyncLoginProtocol). | ✅ |
| `message_keys.py` | 模块 | Baileys key of each inbound message (`inbound_message_key`) and the bounded `MessageKeys` memory the channel fills on inbound and `react_to_message` reads, so a reaction quotes the key as received (group `participant`, raw LID `remoteJid`). | ✅ |
| `bridge/` | 子目录 | Node.js Baileys bridge 子进程（`whatsapp-bridge.js`）及其 npm 依赖。见 [`bridge/_ARCH.md`](bridge/_ARCH.md)。 | — |
