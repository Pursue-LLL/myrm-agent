# messageStream/

## 架构概述

聊天 SSE 流式 reducer 子系统。将 `AgentStreamEvent` 合并进 `Message` 状态。

- **入口**：`handleMessageStream.ts`（dispatcher：mascot 副作用 + 顺序调用 `handlers/*`）
- **切片**：[`handlers/`](handlers/_ARCH.md) 按事件域拆分（companion / tools / completion 等）
- **纯函数**：`streamHelpers.ts`、`fileDiffMerge.ts`、`textSanitize.ts`、`skillManageBatchLink.ts`、`disclosure.ts`
- **上下文**：`streamContext.ts`（`StreamCtx`、`done()`）

## 文件清单

| 文件 / 目录                  | 地位 | 职责                                                                                                                                                                                                                                                                              | I/O/P |
| ---------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `types.ts`                   | 核心 | `StreamHandlerState`（含 `chatId`：发送时快照的 stream 归属 chat，供新 chat 首轮在 messages 为空时解析 chatId；`actionMode`：发送时快照的执行模式，审批卡片按 stream 自身模式归属；`messages` 等字段是 stream 打开时的快照，读不到本轮 assistant 消息，message 状态只能经 `StreamHandlerActions.setMessages` 的 draft 读写） / `StreamHandlerActions` | ✅    |
| `streamContext.ts`           | 核心 | 每事件 handler 上下文与 `done()`                                                                                                                                                                                                                                                  | ✅    |
| `handleMessageStream.ts`     | 核心 | SSE 事件分发器                                                                                                                                                                                                                                                                    | ✅    |
| `handlers/index.ts`          | 核心 | `STREAM_EVENT_HANDLERS` 顺序表                                                                                                                                                                                                                                                    | ✅    |
| `handlers/handlerDeps.ts`    | 辅助 | 切片共享 import                                                                                                                                                                                                                                                                   | ✅    |
| `handlers/*.ts`              | 核心 | 各 `AgentEventType` 域的状态合并                                                                                                                                                                                                                                                  | ✅    |
| `handlers/__tests__/gapEvents.test.ts` | 测试 | CAPABILITY_GAP / SKILL_GAP 一键开启与绑定                                                                                                                                                                                                                                         | ✅    |
| `streamHelpers.ts`           | 辅助 | 来源合并、澄清表单 unwrap（`resolveClarificationFormFromEventData`）、澄清 resume/legacy 判定（`resolveClarifyIsResumeMode`，与 server SSOT 同规则：仅 `source=deep_research` 走 legacy，其余续跑；live handler 与 hydrate 共用）、Goal 归一化、`getUserFriendlyError`（`concurrency_limit` kind 的 i18n 兜底文案，供 `diagnostic_result` 缺失时呈现）                                                                                         | ✅    |
| `fileDiffMerge.ts`           | 辅助 | FILE_DIFF 路径匹配与 diff 择优合并                                                                                                                                                                                                                                                | ✅    |
| `textSanitize.ts`            | 辅助 | 流式文本控制字符剥离                                                                                                                                                                                                                                                              | ✅    |
| `skillManageBatchLink.ts`    | 辅助 | skill_manage 批次提交（服务端 `tool_end` 事件携带 `skill_mutation_batch_id`）关联到仍在等待批次的最新 skill_manage 步骤，使撤销入口在回合进行中即出现；与服务端 `mutation_batch_stream.link_batch_to_step` 同一配对规则                                                           | ✅    |
| `disclosure.ts`              | 辅助 | `applyDisclosureMetadata`：把 MESSAGE_END 的披露字段（`deliverable_tier` → 证据档徽章、`staged_artifacts` → 暂存草案横幅）映射到消息对象，实时事件与持久化元数据共用同一组键 | ✅    |
| `lastMessage.ts`             | 辅助 | `readLastMessage`：经 stream 自己的 `setMessages` 读取聊天当前最后一条 message（返回 immer `current` 拷贝，draft 结束后仍可读）。stream 快照读不到本轮 message，MESSAGE_END 触发后续建议时用它                                                                                    | ✅    |
| `streamWatchdog.ts`          | 核心 | 客户端流式完成状态机看门狗，静默与 EOF 兜底自愈，杜绝回复完成后 UI 假死卡在生成中；只恢复 UI 状态，不触发后续建议（静默 / usage 自愈可能发生在回答仍在流式输出时，只有 MESSAGE_END 能确认回答已完成）                                                                             | ✅    |

## 依赖

- `../types/`（`../types.ts` barrel）— `AgentStreamEvent`、`Message` 等
- `../schema.ts` + `../knownSseEventTypes.ts` — SSE `type` 白名单与 harness 别名
- `./types.ts` — `StreamHandlerState` / `StreamHandlerActions`（本目录专用）
- `../messageUtils.ts`, `../memoryCitationUtils.ts`, `../archiveRestoreActions.ts`

## 入口

上层通过 `../messageStreamHandler.ts` 导入，保持路径稳定。
