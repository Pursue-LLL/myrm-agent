# hooks/voice/

全双工/PTT 语音会话：STT、TTS、OpenAI Realtime、Gemini Live、Agent WebSocket bridge。

## 文件清单

| 文件                     | 职责                                                                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `useVoiceSession.ts`     | 会话编排（barge-in、PTT context 与截图、TTS queue 安全插入）                                                                                                             |
| `useSpeechInput.ts`      | 多后端 STT 输入与主机就绪零延迟门禁（防盲录）                                                                                                                            |
| `useTTS.ts`              | TTS 输出（browser + API）                                                                                                                                                |
| `useVoiceAgentBridge.ts` | 服务端 Agent WebSocket bridge 与主机就绪连接守卫                                                                                                                         |
| `useRealtimeVoice.ts`    | OpenAI Realtime WebRTC                                                                                                                                                   |
| `useGeminiLiveVoice.ts`  | Gemini Live WebSocket                                                                                                                                                    |
| `useLiveMeetingNotes.ts` | 会中实时纪要会话：final 转录入队上报（单飞 + 逐行 `line_id` 幂等）+ 滚动结构化纪要快照                                                                                   |
| `useVoicePttListener.ts` | Tauri PTT → DOM CustomEvent                                                                                                                                              |
| `voiceCommands.ts`       | 语音指令纯函数（停词精确匹配，句中口述不触发）                                                                                                                           |
| `voiceDeviceSettings.ts` | 语音设置（会话开关、全双工、Agent 桥接、模式）的设备端共用读写层：设置页写、聊天语音按钮读；浏览器拒绝存储时在本页内保留，本页写入与其他标签的改动都会通知读取方 |

## 依赖

- `@/store/*`、`@/services/*` — 配置与 API
- 消费者：`message-input-actions/`、`features/voice/`、`app-shell/voice-ptt-initializer.tsx`、设置页 `settings/sections/personal/VoiceSessionToggles.tsx` 与 `settings/sections/integration/channels/VoiceSessionModeSettings.tsx`（经 `voiceDeviceSettings`）

## 约束

- 域内相对 import（`./useTTS`）；域外 import 路径 `@/hooks/voice/<file>`
