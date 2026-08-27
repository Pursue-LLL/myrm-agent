# hooks/voice/

全双工/PTT 语音会话：STT、TTS、OpenAI Realtime、Gemini Live、Agent WebSocket bridge。

## 文件清单

| 文件                     | 职责                                                          |
| ------------------------ | ------------------------------------------------------------- |
| `useVoiceSession.ts`     | 会话编排（barge-in、vision、PTT context、TTS queue 安全插入） |
| `useSpeechInput.ts`      | 多后端 STT 输入与主机就绪零延迟门禁（防盲录）                   |
| `useTTS.ts`              | TTS 输出（browser + API）                                     |
| `useVoiceAgentBridge.ts` | 服务端 Agent WebSocket bridge 与主机就绪连接守卫              |
| `useRealtimeVoice.ts`    | OpenAI Realtime WebRTC                                        |
| `useGeminiLiveVoice.ts`  | Gemini Live WebSocket                                         |
| `useVoicePttListener.ts` | Tauri PTT → DOM CustomEvent                                   |

## 依赖

- `@/store/*`、`@/services/*` — 配置与 API
- `../multimodal/useCameraInput.ts`、`../multimodal/useVisionIntent.ts` — 跨域组合依赖
- 消费者：`message-input-actions/`、`features/voice/`、`app-shell/voice-ptt-initializer.tsx`

## 约束

- 域内相对 import（`./useTTS`）；域外 import 路径 `@/hooks/voice/<file>`
