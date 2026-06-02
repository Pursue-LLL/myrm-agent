# api/tts 模块架构


---

## 架构概述

文字转语音 (Text-to-Speech) API 端点。为 Web 前端提供完整合成和流式合成两种模式，复用用户的 VoiceConfig 配置。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 入口 | 模块声明 | ❌ |
| `router.py` | ✅ 核心 | TTS 合成端点：`/synthesize`（完整文件）+ `/synthesize-stream`（流式 MP3） | ❌ |

---

## 依赖关系

### 内部依赖
- `app.channels.types`：VoiceConfig
- `../../api/dependencies`：用户认证

### 外部依赖
- `fastapi`：路由、FileResponse、StreamingResponse
