# messageStream/

## 架构概述

聊天 SSE 流式 reducer 子系统。将 `AgentStreamEvent` 合并进 `Message` 状态；主逻辑在 `handleMessageStream.ts`，纯函数在 `streamHelpers.ts` / `fileDiffMerge.ts`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.ts` | 核心 | `StreamHandlerState` / `StreamHandlerActions` | ✅ |
| `handleMessageStream.ts` | 核心 | 按 `AgentEventType` 分支更新消息 | ✅ |
| `streamHelpers.ts` | 辅助 | 来源合并、澄清表单、Goal 归一化 | ✅ |
| `fileDiffMerge.ts` | 辅助 | FILE_DIFF 路径匹配与 diff 择优合并 | ✅ |
| `textSanitize.ts` | 辅助 | 流式文本控制字符剥离 | ✅ |

## 依赖

- `../types.ts` — 事件与消息类型
- `../messageUtils.ts`, `../memoryCitationUtils.ts`, `../archiveRestoreActions.ts`

## 入口

上层通过 `../messageStreamHandler.ts` 导入，保持路径稳定。
