# api/voice/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `agent_bridge.py` | 模块 | Agent execution bridge for voice sessions. Handles parameter assembly, streaming Agent execution, sentence-split TTS pipeline, turn management, and working-resp | ✅ |
| `realtime.py` | 模块 | OpenAI Realtime API integration endpoints. Enables sub-300ms voice latency by connecting browser directly to OpenAI via WebRTC. """ | ✅ |
| `ws_session.py` | 模块 | Full-duplex voice session WebSocket endpoint. | ✅ |
