# channels/providers/feishu/sdk/

## 架构概述

本目录模块说明。上级文档：[../../../../_ARCH.md](../../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Package init for feishu SDK. Re-exports the public API surface | ✅ |
| `_documents.py` | 模块 | Mixin that adds document-level API methods to FeishuClient: Drive meta, comments, | ✅ |
| `_messaging.py` | 模块 | Mixin that adds IM messaging, reactions, and media methods to FeishuClient | ✅ |
| `client.py` | 模块 | Standalone Feishu OpenAPI client | ✅ |
| `exceptions.py` | 模块 | Feishu-specific API error hierarchy. When used inside a channel provider, | ✅ |
