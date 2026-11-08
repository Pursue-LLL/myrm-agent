# channels/voice/tts/

## 架构概述

出站 TTS：入口与提供方实现分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 synthesize / synthesize_stream / 可用性探测与测试依赖的辅助 | ✅ |
| `common.py` | 辅助 | 默认 URL/音色、超时、安装提示、可用性探测、临时文件与摘要 | ✅ |
| `core.py` | 核心 | 单次与流式语音合成入口、失败回退 | ✅ |
| `providers.py` | 核心 | OpenAI/ElevenLabs/Fish/MiniMax/Voicebox/Piper/Edge 的请求与流式实现 | ✅ |

## 依赖关系

- `core.py` → `common.py`
- `core.py` → `providers.py`
- `providers.py` → `common.py`
