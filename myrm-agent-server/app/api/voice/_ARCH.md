# api/voice/

## 架构概述

实时语音 WebSocket 与 REST 会话控制。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `agent_bridge.py` | 模块 | Agent execution bridge for voice sessions. | ✅ |
| `gemini_live.py` | 模块 | Gemini Live API integration endpoints (ephemeral token + WebSocket URL). | ✅ |
| `realtime.py` | 模块 | OpenAI Realtime API integration endpoints. | ✅ |
| `ws_session.py` | 模块 | Full-duplex voice session WebSocket endpoint. | ✅ |
