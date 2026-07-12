# lib/vision/

语音+视觉多模态会话纯函数（帧选择、会话状态机）。

| 文件 | 职责 |
|------|------|
| `frameSelector.ts` | 视频帧采样策略 |
| `speechVisualSession.ts` | 语音视觉会话生命周期 |

消费者：`store/chat/multimodalBuilder.ts`、`hooks/useVoiceSession.ts`。
