# hooks/voice/session/

语音会话编排器 [`../useVoiceSession.ts`](../useVoiceSession.ts) 的内部模块：PTT 屏幕上下文融合、传输状态同步、窗口事件桥与 TTS 断句。编排器是唯一对外入口，这里的模块只被它引用。

## 文件清单

| 文件                     | 职责                                                                                                                                                                                          |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`               | 会话状态 `VoiceSessionState` 与传输模式 `VoiceSessionMode`，由 `useVoiceSession.ts` 重新导出                                                                                                  |
| `speakableSegments.ts`   | 纯函数：回复文本按句末符号切成可朗读片段，末尾没有终止符的残片单独保留                                                                                                                        |
| `usePttScreenContext.ts` | PTT 屏幕上下文融合：缓存 `voice-ptt-context`（截图、窗口标题、选中文本或屏幕文字），转写到达时附加到消息；PTT 模式下截图仍在传输时最多等待 250 ms，超过 30 s 的上下文丢弃，每份上下文只用一次 |
| `useSessionStateSync.ts` | 把当前模式对应的传输（Agent bridge / OpenAI Realtime / Gemini Live）的连接状态映射为会话状态；传输断开且会话仍在运行时结束会话；其他模式的传输状态不参与                                        |
| `useSessionEvents.ts`    | 窗口事件桥：`myrm-voice-toggle` / `myrm-voice-interrupt` / `myrm-voice-replay` 驱动会话，`myrm-voice-state-update` 对外广播会话状态与音量                                                      |

## 测试

`__tests__/` 每个 hook 一份：`usePttScreenContext`（融合格式、截图屏障与 30 s 过期、一次性消费）、`useSessionStateSync`（三种传输的状态映射与断开收尾）、`useSessionEvents`（事件分发、卸载解绑、状态广播）。断句函数的用例在 `src/__tests__/hooks/extractSpeakableSegments.test.ts`。

## 依赖

- 同域 [`../useVoicePttListener.ts`](../useVoicePttListener.ts)（`PttScreenContext`）、[`../useSpeechInput.ts`](../useSpeechInput.ts)（`SpeechMode`）、[`../useVoiceAgentBridge.ts`](../useVoiceAgentBridge.ts) / [`../useRealtimeVoice.ts`](../useRealtimeVoice.ts) / [`../useGeminiLiveVoice.ts`](../useGeminiLiveVoice.ts)（连接状态类型）
- 父模块 [`../_ARCH.md`](../_ARCH.md)

## 约束

- 只被 `../useVoiceSession.ts` 引用；域外消费者经 `@/hooks/voice/useVoiceSession` 取会话类型，不直接引用本目录
