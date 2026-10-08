# hooks/message-input/

聊天输入域：输入框编排、附件上传、排队发送、流式渲染、@ 引用、Slash 命令、输入历史、Wiki 证据复问口径、单轮能力覆写可观测埋点。

## 文件清单

| 文件                                 | 职责                                                                                                                                                                                                                                |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useMessageInput.ts`                 | 输入框状态、提交编排、草稿、与 queue/upload/wiki 组合；agent 忙且带附件时改走排队（redirect/steer 只带文本）；无痕模式不写草稿与输入历史                                                                                            |
| `useMessageQueue.ts`                 | 排队消息的会话级薄 hook：绑定 `useMessageQueueStore` 当前会话切片，负责 localStorage 持久化与水合（无痕仅内存）；`enqueue` 返回真实队列位置；输入框与工件选区动作共享同一队列                                                       |
| `useQueueDrain.ts`                   | 排队消息出队循环：单飞认领队首（编辑中的消息不出队）、Stop 后暂停、busy 阶梯退避用尽或请求被本地拒绝后转 stuck 交由用户重试（stuck 文案保持中性，不断言原因）；队首随自身附件（`queuedAttachments`）发送，不占用输入框当前附件      |
| `messageInputKeyRouter.ts`           | 聊天输入框双通道键盘交互路由核心：判定 Enter（引导纠偏）与 Alt+Enter（非中断排队跟进）、IME 组合态守卫与多行编辑换行；展开编辑器内 Enter 换行、Ctrl/⌘+Enter 发送                                                                    |
| `turnCapabilityOverrideCore.ts`      | 本轮能力覆写核心：按 Agent 基线归一化 Skill/MCP 子集并构建 `agentConfigOverride`                                                                                                                                                    |
| `turnCapabilityTelemetry.ts`         | 单轮能力覆写埋点：`useTurnCapabilityTelemetry` 统一提交/入队/忙碌回队/终态埋点，`resolveTerminalTelemetry` 生成请求体终态遥测；直发与出队共用同一口径                                                                               |
| `useDesktopFolderDrop.ts`            | 桌面端原生文件夹拖拽监听、POSIX 路径规范化、会话目录即时预授权                                                                                                                                                                      |
| `useInputFileUpload.ts`              | 粘贴/拖拽上传、Office 文本优先智能识别、非阻塞乐观入队与异步进度流水线、SHA-256 去重、分级大小校验                                                                                                                                  |
| `useInputHistory.ts`                 | ArrowUp 空框输入历史（per-agent localStorage）                                                                                                                                                                                      |
| `useMessageInputWikiEvidenceCore.ts` | Wiki 证据复问口径与 steer success 挂起确认                                                                                                                                                                                          |
| `useReferenceMention.ts`             | `@` 引用 autocomplete（workspace/wiki/**@chat: prior_chat**；`@chat:` 走 **`searchCitableChats` → `/chats/recall/search`** recall SSOT，**不依赖** composer `chatId`，EmptyChat 可用）                                              |
| `useSlashCommand.ts`                 | `/` Slash 命令面板；skill 选中写入 pendingExplicitSkillActivation + chip；执行时仅移除 `/命令` 保留前后文本（命令名 token 与技能命名规则一致——允许连字符，面板检测/命令移除/Esc 共用 `SLASH_COMMAND_SUFFIX_RE` 单一正则，语义一致） |
| `useSmoothStream.ts`                 | 流式 markdown 平滑渲染（message-box 消费）                                                                                                                                                                                          |
| `useComposerContextChips.ts`         | 输入区上下文挂载项统一聚合 Hook：提取工作流模板、显式技能、单轮能力范围、会话级挂载知识库、@ 引用，配合 AttachList 进行动静分层并计算负载过载信息                                                                                   |

## 依赖

- `@/store/useChatStore`、`@/store/chat/*` — 聊天状态与归档恢复
- `@/store/chat/useMessageQueueStore` — 排队消息内存状态源（`useMessageQueue` / `useQueueDrain` 共用，`stopMessage` 暂停）
- `@/hooks/billing/useQuotaGuard`、`@/hooks/shared/useDraftPersistence` — 跨域依赖
- 消费者：`components/features/chat-window/`、`message-box/MarkdownContent.tsx`、`artifacts/portal/useSelectionAction.ts`

## 约束

- 域内相对 import（`./useMessageQueue`）；域外 import 路径 `@/hooks/message-input/<file>`
