# hooks/multimodal/

摄像头与视觉意图（语音会话使用）。

| 文件                 | 职责                             |
| -------------------- | -------------------------------- |
| `useCameraInput.ts`  | 摄像头生命周期、帧缓冲、snapshot |
| `useVisionIntent.ts` | 双语规则判断是否需要视觉上下文   |

消费者：`voice/useVoiceSession`。
