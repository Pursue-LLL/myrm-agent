# channels/providers/_ilink/

## 架构概述

iLink **共享协议库**（非独立渠道）：WeChat/WhatsApp 等 Provider 复用的 Bot 协议客户端、加解密与媒体处理。目录名 `_ilink` 遵循 providers 层 `_` 前缀共享库约定。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | iLink shared library — WeChat bridge protocol client, crypto, media, and types. | ✅ |
| `client.py` | 模块 | iLink Bot protocol HTTP client. Single-instance httpx connection reuse with unified exception mapping. | ✅ |
| `crypto.py` | 模块 | WeChat iLink media encryption utility. Uses AES-128-ECB mode (per WeChat CDN requirements). | ✅ |
| `media.py` | 模块 | iLink media processing utility functions. Inbound parsing and outbound upload, zero state dependencies. | ✅ |
| `silk.py` | 模块 | WeChat voice format converter (SILK→WAV). Optional dep `pilk` via extra `wechat-silk` or harness `platform.wechat-silk` lazy install. | ✅ |
| `types.py` | 模块 | Pure data type definitions and serialization utilities for the iLink Bot protocol. | ✅ |
