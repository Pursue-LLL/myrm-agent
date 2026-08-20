# hooks/message-input/

聊天输入域：输入框编排、附件上传、排队发送、流式渲染、@ 引用、Slash 命令、输入历史、Wiki 证据复问口径、单轮能力覆写可观测埋点。

## 文件清单

| 文件                                 | 职责                                                                                                                                                                                                                                |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useMessageInput.ts`                 | 输入框状态、提交编排、草稿、与 queue/upload/wiki 组合                                                                                                                                                                               |
| `useMessageQueue.ts`                 | Agent busy 时消息排队状态机                                                                                                                                                                                                         |
| `turnCapabilityOverrideCore.ts`      | 本轮能力覆写核心：按 Agent 基线归一化 Skill/MCP 子集并构建 `agentConfigOverride`                                                                                                                                                    |
| `useDesktopFolderDrop.ts`            | 桌面端原生文件夹拖拽监听、POSIX 路径规范化、会话目录即时预授权                                                                                                                                                                      |
| `useInputFileUpload.ts`              | 粘贴/拖拽上传、Office 文本优先智能识别、非阻塞乐观入队与异步进度流水线、SHA-256 去重、分级大小校验                                                                                                                                  |
| `useInputHistory.ts`                 | ArrowUp 空框输入历史（per-agent localStorage）                                                                                                                                                                                      |
| `useMessageInputWikiEvidenceCore.ts` | Wiki 证据复问口径与 steer success 挂起确认                                                                                                                                                                                          |
| `useReferenceMention.ts`             | `@` 引用 autocomplete（workspace/wiki/**@chat: prior_chat**；`@chat:` 走 **`searchCitableChats` → `/chats/recall/search`** recall SSOT，**不依赖** composer `chatId`，EmptyChat 可用）                                              |
| `useSlashCommand.ts`                 | `/` Slash 命令面板；skill 选中写入 pendingExplicitSkillActivation + chip；执行时仅移除 `/命令` 保留前后文本（命令名 token 与技能命名规则一致——允许连字符，面板检测/命令移除/Esc 共用 `SLASH_COMMAND_SUFFIX_RE` 单一正则，语义一致） |
| `useSmoothStream.ts`                 | 流式 markdown 平滑渲染（message-box 消费）                                                                                                                                                                                          |

## 依赖

- `@/store/useChatStore`、`@/store/chat/*` — 聊天状态与归档恢复
- `@/hooks/billing/useQuotaGuard`、`@/hooks/shared/useDraftPersistence` — 跨域依赖
- 消费者：`components/features/chat-window/`、`message-box/MarkdownContent.tsx`、`artifacts/portal/useSelectionAction.ts`

## 约束

- 域内相对 import（`./useMessageQueue`）；域外 import 路径 `@/hooks/message-input/<file>`
