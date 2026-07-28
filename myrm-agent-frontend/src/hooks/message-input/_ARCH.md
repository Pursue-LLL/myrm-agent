# hooks/message-input/

聊天输入域：输入框编排、附件上传、排队发送、流式渲染、@ 引用、Slash 命令、输入历史、Wiki 证据复问口径。

## 文件清单

| 文件 | 职责 |
|------|------|
| `useMessageInput.ts` | 输入框状态、提交编排、草稿、与 queue/upload/wiki 组合 |
| `useMessageQueue.ts` | Agent busy 时消息排队状态机 |
| `useInputFileUpload.ts` | 粘贴/拖拽上传、SHA-256 去重、分级大小校验 |
| `useInputHistory.ts` | ArrowUp 空框输入历史（per-agent localStorage） |
| `useMessageInputWikiEvidenceCore.ts` | Wiki 证据复问口径与 steer success 挂起确认 |
| `useReferenceMention.ts` | `@` 引用 autocomplete |
| `useSlashCommand.ts` | `/` Slash 命令面板 |
| `useSmoothStream.ts` | 流式 markdown 平滑渲染（message-box 消费） |

## 依赖

- `@/store/useChatStore`、`@/store/chat/*` — 聊天状态与归档恢复
- `@/hooks/billing/useQuotaGuard`、`@/hooks/shared/useDraftPersistence` — 跨域依赖
- 消费者：`components/features/chat-window/`、`message-box/MarkdownContent.tsx`、`artifacts/portal/useSelectionAction.ts`

## 约束

- 域内相对 import（`./useMessageQueue`）；域外 import 路径 `@/hooks/message-input/<file>`
