# channels/providers/feishu/

## 架构概述

飞书 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Feishu/Lark channel provider — bidirectional messaging via Open API. | ✅ |
| `api.py` | 模块 | Re-export of Feishu SDK public surface. Canonical source: .sdk.client. | ✅ |
| `cards.py` | 模块 | Feishu card builders, post format builders, and streaming text utilities. | ✅ |
| `channel.py` | 模块 | Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging. Default transport: **websocket** (outbound, no public IP). | ✅ |
| `comment_content.py` | 模块 | Comment content extraction and prompt construction. Pure functions, zero I/O (except wiki link resolution which requires FeishuClient). | ✅ |
| `comment_handler.py` | 模块 | Feishu drive document comment handler. Converts comment events to InboundMessage | ✅ |
| `models.py` | 模块 | Pydantic models for Feishu/Lark event subscription webhook payloads. | ✅ |
| `parser.py` | 模块 | Feishu inbound message parser. Converts Feishu event JSON to structured data. Supports post rich-text -> Markdown, @mention detection, and image/media key extra | ✅ |
| `registration.py` | 模块 | Channel provider utility. Encapsulates the Feishu device-code registration flow for automated bot app provisioning. Used by server-layer endpoints. | ✅ |
| `webhook_utils.py` | 模块 | Feishu Webhook utility functions for signature verification and metadata extraction. No full FeishuChannel instantiation needed. Suitable for control planes and | ✅ |
| `ws_transport.py` | 模块 | Feishu WebSocket transport — long-lived connection via lark-oapi SDK. | ✅ |
