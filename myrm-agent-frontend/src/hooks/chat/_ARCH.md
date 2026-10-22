# hooks/chat 模块架构

会话级 UX Hook 子目录：首轮发送预热与跨会话 cite 拖拽投递。

## 文件清单

| 文件                          | 地位 | 职责                                                                                                                                                                                                                                                                                                                                | I/O/P |
| ----------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `useChatTurnPrewarm.ts`       | 核心 | 空会话挂载 + 输入框聚焦 + 切 Agent 时的首轮 turn 预热触发/取消（幂等，模块级 inflight map 去重；`autoOnMount` 卸载不取消以保住 EmptyChat→Chat 首次发送的预热）                                                                                                                                                                      | ✅    |
| `usePriorChatComposerDrop.ts` | 核心 | 侧栏会话拖拽到 Composer 的 cite 投递（`prior_chat` MIME 载荷解码、同会话拒绝、`addMentionReference` 注入 + 输入框聚焦）                                                                                                                                                                                                             | ✅    |
| `usePresenceReadMark.ts`      | 核心 | 在用户在场时盖章当前会话（`markChatAsRead`，静默）：会话有内容时打开、窗口回到前台、该会话回合在用户注视下结束（`run-digest-updated` 终态）、用户停止注视（窗口失焦 / 页面隐藏 / 离开会话；失焦与隐藏按跨事件在场状态只盖一次，离开会话仅在页面仍在场时盖章）；`isUserPresent()` 为唯一在场判定；会话尚无内容（服务端未建行）不盖章 | ✅    |

## 依赖

- `useChatTurnPrewarm` → `@/services/chat`（prewarm REST）、`@/store/useChatStore`
- `usePriorChatComposerDrop` → `@/lib/chat/priorChatDrag`、`@/store/useChatStore`、`@/hooks/ui/useDragDrop`

## 测试

| 位置         | 说明                                     |
| ------------ | ---------------------------------------- |
| `__tests__/` | hook 单元测试与实现同域共置（colocated） |
