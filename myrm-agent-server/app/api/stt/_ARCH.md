# api/stt/

## 架构概述

语音转文字 HTTP/WebSocket 流式层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Speech-to-Text API；local provider 未装 `local-stt` extra 时 `/transcribe` 返回 503（与 TTS Edge 守卫对称） | ✅ |
| `ws_stream.py` | 模块 | WebSocket STT streaming；local provider 未装 `local-stt` extra 时返回 error JSON + 关闭连接 | ✅ |
