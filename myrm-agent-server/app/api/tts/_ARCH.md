# api/tts/

## 架构概述

TTS 合成 HTTP 层，供 Web 前端消息朗读（`useTTS`）调用。上级文档：[../_ARCH.md](../_ARCH.md)。

- `POST /synthesize`：完整 MP3 下载；无音频 → 422
- `POST /synthesize-stream`：分块流式 MP3；首 chunk 前探测，无音频 → 422
- Web 朗读配置：`extract_web_tts_config`（不要求频道 `ttsMode`）；频道仍用 `extract_voice_config`
- `tts_provider=edge` 且未安装 `voice-tts` extra → 503（detail 含 `uv sync --extra voice-tts`）

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Text-to-Speech API | ✅ |
