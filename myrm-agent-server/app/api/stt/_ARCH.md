# api/stt 模块架构


---

## 架构概述

语音转文字 (Speech-to-Text) API。双模式：REST 批量转写 + WebSocket 实时流式转写。
支持 4 个 provider: Local Whisper (免费) / OpenAI / Groq / Deepgram。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 入口 | 模块声明 | ❌ |
| `router.py` | ✅ 核心 | REST 批量 STT + GET /stt/status（本地 STT 状态查询） | ❌ |
| `ws_stream.py` | ✅ 核心 | WebSocket 流式 STT，代理音频流到 Deepgram 等提供商，返回 interim/final transcript | ❌ |

---

## 架构特性

- **流式 STT**：WebSocket `/ws/stt/stream`，音频块实时转发到 Deepgram，返回 interim/final 结果
- **本地 STT**：provider=local 时使用 faster-whisper 本地推理，免费、隐私优先、无需 API Key
- **Keyterms**：从客户端接收上下文关键词，传递给 STT 提供商提升识别准确率（URL 安全编码）
- **提供商自动降级**：不支持流式的提供商（如 OpenAI Whisper、Local）自动 fallback 到批量模式
- **状态查询**：GET `/stt/status` 返回本地 STT 可用性和模型加载状态
- **单租户认证**：WebSocket 复用 HTTP 中间件注入的身份；Sandbox 模式要求 `SANDBOX_API_KEY`，本地模式允许回环请求
- **会话超时**：120s 无音频数据自动关闭 WS，防止资源泄漏

---

## 依赖关系

### 内部依赖
- `app.channels.types`：VoiceConfig
- `app.channels.voice.stt`：batch transcribe
- `../../api/dependencies`：REST 用户认证
- `../../middleware/auth.py`：WebSocket 身份注入与沙箱 API Key 校验

### 外部依赖
- `fastapi`：路由、WebSocket、文件上传
- `websockets`：Deepgram WebSocket 客户端（通过 myrm-agent-harness 传递）
