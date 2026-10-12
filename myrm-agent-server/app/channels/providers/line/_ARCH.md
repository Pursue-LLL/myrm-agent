# channels/providers/line/

## 架构概述

LINE 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | LINE channel provider via Messaging API. | ✅ |
| `api.py` | 模块 | LINE HTTP layer. Called by channel.py via self._api. | ✅ |
| `channel.py` | 模块 | LINE integration: credentials, lifecycle, Reply/Push outbound and quote-token context linking; composes `LINEInboundMixin`. Outbound batches >5 messages across multiple push/reply API calls (Item 46). | ✅ |
| `helpers.py` | 模块 | LINE webhook type definitions and constants. Referenced by channel.py and inbound.py. | ✅ |
| `inbound.py` | 模块 | `LINEInboundMixin`: webhook signature check, event routing, message / postback parsing, sender name resolution and mention detection. | ✅ |
| `user_resolver.py` | 模块 | LINE user resolver. Resolves display names via 1:1 / group / room profile APIs with scope-aware caching. | ✅ |
