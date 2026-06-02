# api/voice 模块架构


---

## 架构概述

全双工语音会话系统，支持三种运行模式：

- **audio_only**（默认）：纯 STT + TTS 音频 I/O，Agent 调用由前端通过 SSE API 发起
- **agent_bridge**：STT → 服务端 Agent 执行 → 句级流式 TTS，消除前端往返延迟
- **openai_realtime**：OpenAI Realtime API + WebRTC 直连，浏览器与 OpenAI 建立 P2P 音频通道，sub-300ms 延迟，工具调用通过后端代理执行

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 入口 | 模块声明 | ❌ |
| `ws_session.py` | ✅ 核心 | WebSocket `/ws/voice/session`：并发 STT 流式转写 + 按需 TTS / Agent Bridge | ✅ |
| `agent_bridge.py` | ✅ 核心 | 语音 Agent 桥接：服务端 Agent 执行 + 句级 TTS 流水线 + Turn 管理 | ✅ |
| `realtime.py` | ✅ 核心 | OpenAI Realtime API 支持：Ephemeral Token 签发 + 工具执行代理 + 语音记录持久化 | ✅ |

---

## 架构特性

- **三模式**：`audio_only` 保持兼容性；`agent_bridge` 提供低延迟服务端 Agent 集成；`openai_realtime` 提供极致延迟的端到端语音（sub-300ms）
- **全双工**：STT 和 TTS 在同一 WebSocket 上并发运行，前端可在 TTS 播放期间保持 STT 监听
- **barge-in**：前端发送 `tts_cancel` 消息立即中断 TTS 和 Agent 执行
- **句级流式 TTS**：Agent 输出在句子边界拆分，每句独立 TTS，降低首字节延迟
- **Turn 管理**：新语音输入自动取消上一轮 Agent 执行，通过 CancellationToken 实现
- **Working Hint**：Agent 处理期间自动播报 "处理中" 提示，填补等待空白
- **审批事件透传**：Agent 流中的 `approval_required` / `tool_approval_request` 事件被捕获后通过 TTS 告知用户并通过 WS 转发给前端，前端复用已有 `ToolApprovalDialog` 弹出审批 UI
- **复用现有能力**：STT 复用 Deepgram 代理模式，TTS 复用 `synthesize_stream`，Agent 复用 `ai_agent_service_stream`
- **Provider fallback**：不支持流式 STT 的提供商自动降级到批量模式
- **WS 并发安全**：`_VoiceSession` 与 `VoiceAgentBridge` 共享 `asyncio.Lock` 序列化所有 WebSocket send 操作，防止并发写入导致协议错误
- **Task 异常可观测**：fire-and-forget `asyncio.create_task` 通过 `add_done_callback` 捕获异常并回传前端 error 事件
- **Turn 耗时可观测**：每轮 Agent 执行完成后输出 INFO 日志（params_assembly / agent_tts / total），便于生产定位性能瓶颈
- **前端 TTS 播放队列**：句级 TTS 音频通过队列顺序播放，避免 TTS 生成快于播放时多句重叠

---

## agent_bridge 模式协议

```
C→S: {"type": "config", "mode": "agent_bridge", "agent_id": "...", "chat_id": "...", "keyterms": [...]}
C→S: binary audio (webm/opus)
C→S: {"type": "tts_cancel"}     — barge-in
C→S: {"type": "close"}          — end session

S→C: {"type": "stt_interim", "text": "..."}
S→C: {"type": "stt_final", "text": "..."}
S→C: {"type": "agent_thinking", "turn_id": "..."}
S→C: {"type": "agent_response", "text": "...", "turn_id": "...", "done": false|true}
S→C: {"type": "agent_tool_use", "tool_name": "...", "turn_id": "..."}
S→C: {"type": "tts_start"} + binary TTS audio + {"type": "tts_end"}
S→C: {"type": "approval_required", "turn_id": "...", "data": {...}}
S→C: {"type": "tool_approval_request", "turn_id": "...", "data": {...}, "messageId": "..."}
S→C: {"type": "agent_done", "turn_id": "..."}
S→C: {"type": "agent_error", "message": "..."}
S→C: {"type": "error", "message": "..."}
```

---

## openai_realtime 模式架构

```
浏览器 ──WebRTC P2P──→ OpenAI Realtime API (音频 + VAD + LLM + TTS)
   │                            │
   │ data channel events        │ function_call_arguments.done
   │                            │
   ├─ POST /voice/realtime-token ← 后端签发 Ephemeral Token (含 instructions/tools)
   ├─ POST /voice/realtime-tool-exec ← 前端代理工具调用至后端 Agent 执行
   └─ POST /voice/realtime-transcript ← 会话结束后持久化文本记录
```

**设计要点**：
- 音频流在浏览器与 OpenAI 之间 P2P 传输，后端不中转音频，延迟最低
- 后端仅负责：Token 签发（注入 system prompt + tools 定义）、工具安全执行、记录持久化
- ICE 连接超时（3s）自动 fallback 至 `agent_bridge` 模式，保证可用性
- Function Calling 通过后端 `ai_agent_service_stream` 代理，确保工具在 Agent 安全上下文中执行
- 会话结束时前端将 transcript buffer 批量写入 chat history，保持消息记录完整性

---

## 依赖关系

### 内部依赖
- `app.channels.types`：VoiceConfig
- `app.channels.voice.tts`：synthesize_stream
- `app.channels.voice.stt`：batch transcribe (fallback)
- `myrm_agent_harness.utils.runtime.cancellation`：CancellationToken (agent_bridge)
- `app.core.infra.ws_origin_guard`：WebSocket Origin 验证
- `app.core.channel_bridge.config_loader`：用户配置加载
- `app.services.agent.streaming`：ai_agent_service_stream (agent_bridge, realtime tool-exec)
- `app.services.agent.profile_resolver`：AgentProfileResolver (agent_bridge, realtime)
- `app.services.chat.chat_message`：ChatMessageService (realtime transcript 持久化)

### 外部依赖
- `fastapi`：WebSocket 路由 + REST 端点
- `websockets`：Deepgram WebSocket 客户端
- `httpx`：OpenAI Realtime Session Token 签发 HTTP 调用
