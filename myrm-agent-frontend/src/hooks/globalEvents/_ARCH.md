# hooks/globalEvents/

全局 SSE 编排与跨 feature toast。

| 文件 | 职责 |
|------|------|
| `useGlobalEvents.ts` | SSE 订阅、审批/预算/后台任务/`managed_policy_updated`/`run_digest_updated` 等全局事件编排 |
| `memoryOperationToasts.ts` | 记忆 CRUD toast |
| `locatorHealedToast.tsx` | 浏览器 locator 自愈通知 |
| `messageDeadLetteredToast.ts` | 消息死信告警 |

Hook 层允许的 JSX 例外（toast 渲染）。消费者：`global-events-initializer.tsx`、workspace-browser。
