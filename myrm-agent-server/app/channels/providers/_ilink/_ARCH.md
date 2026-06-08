# channels/providers/_ilink/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 见源码 | — |
| `client.py` | 模块 | iLink Bot protocol HTTP client. Single-instance httpx connection reuse with unified exception mapping | ✅ |
| `crypto.py` | 模块 | WeChat iLink media encryption utility. Uses AES-128-ECB mode (per WeChat CDN requirements) | ✅ |
| `media.py` | 模块 | iLink media processing utility functions. Inbound parsing and outbound upload, zero state dependencies | ✅ |
| `silk.py` | 模块 | WeChat voice format converter. Converts SILK-encoded voice files to WAV format | ✅ |
| `types.py` | 模块 | Pure data type definitions and serialization utilities for the iLink Bot protocol | ✅ |
