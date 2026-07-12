# hooks/globalEvents/

全局 SSE/操作 toast：记忆变更、locator healed、死信等跨 feature 通知。

| 文件 | 职责 |
|------|------|
| `memoryOperationToasts.ts` | 记忆 CRUD toast |
| `locatorHealedToast.tsx` | 浏览器 locator 自愈通知 |
| `messageDeadLetteredToast.ts` | 消息死信告警 |

Hook 层允许的 JSX 例外（toast 渲染）。
