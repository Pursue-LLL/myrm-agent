# hooks/chat 模块架构

会话级 UX Hook 子目录：首轮发送预热与跨会话 cite 拖拽投递。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `useChatTurnPrewarm.ts` | 核心 | 空会话挂载 + 输入框聚焦 + 切 Agent 时的首轮 turn 预热触发/取消（幂等，模块级 inflight map 去重；`autoOnMount` 卸载不取消以保住 EmptyChat→Chat 首次发送的预热） | ✅ |
| `usePriorChatComposerDrop.ts` | 核心 | 侧栏会话拖拽到 Composer 的 cite 投递（`prior_chat` MIME 载荷解码、同会话拒绝、`addMentionReference` 注入 + 输入框聚焦） | ✅ |

## 依赖

- `useChatTurnPrewarm` → `@/services/chat`（prewarm REST）、`@/store/useChatStore`
- `usePriorChatComposerDrop` → `@/lib/chat/priorChatDrag`、`@/store/useChatStore`、`@/hooks/ui/useDragDrop`

## 测试

| 位置 | 说明 |
|------|------|
| `__tests__/` | hook 单元测试与实现同域共置（colocated） |
