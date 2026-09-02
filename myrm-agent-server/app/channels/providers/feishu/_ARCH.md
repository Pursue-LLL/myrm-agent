# channels/providers/feishu/

## 架构概述

飞书 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Feishu/Lark channel provider — bidirectional messaging via Open API. | ✅ |
| `action_fallback.py` | 模块 | Local/intranet ActionButton fallback to numbered text options with (chat,user) session scoping. | ✅ |
| `api.py` | 模块 | Re-export of Feishu SDK public surface. Canonical source: .sdk.client. | ✅ |
| `cards.py` | 模块 | Feishu card builders, post format builders, streaming text utilities, and contact disambiguation / deliverable handoff cards. | ✅ |
| `channel.py` | 模块 | Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging. Outbound `send()` uses `render()` multi-chunk delivery (Item 46). Default transport: **websocket** (outbound, no public IP). | ✅ |
| `comment_content.py` | 模块 | Comment content extraction and prompt construction. Pure functions, zero I/O (except wiki link resolution which requires FeishuClient). | ✅ |
| `comment_handler.py` | 模块 | Feishu drive document comment handler. Converts comment events to InboundMessage | ✅ |
| `contact_fuzzy.py` | 模块 | High-precision phonetic & Levenshtein contact fuzzy matching and disambiguation engine. | ✅ |
| `doctor.py` | 模块 | Feishu channel Doctor diagnostic suite (CardKit streaming permissions, tokens, transport reachability). | ✅ |
| `models.py` | 模块 | Pydantic models for Feishu/Lark event subscription webhook payloads. | ✅ |
| `parser.py` | 模块 | Feishu inbound message parser. Converts Feishu event JSON to structured data. Supports post rich-text -> Markdown, @mention detection, and image/media key extra | ✅ |
| `registration.py` | 模块 | Channel provider utility. Encapsulates the Feishu device-code registration flow for automated bot app provisioning. Used by server-layer endpoints. | ✅ |
| `streaming_dashboard.py` | 模块 | Feishu CardKit streaming dashboard, tool execution header state machine, and 300ms adaptive throttler. | ✅ |
| `table_slicer.py` | 模块 | Feishu 24KB card boundary slicer, Markdown table header preservation, and Lark Markdown cleaner. | ✅ |
| `user_resolver.py` | 模块 | Feishu user resolver using contact API with LRU+TTL caching. Resolves sender display names for group chat context. | ✅ |
| `webhook_utils.py` | 模块 | Feishu Webhook utility functions for signature verification and metadata extraction. No full FeishuChannel instantiation needed. Suitable for control planes and | ✅ |
| `ws_transport.py` | 模块 | Feishu WebSocket transport — long-lived connection via lark-oapi SDK. | ✅ |
