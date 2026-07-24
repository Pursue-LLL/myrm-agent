# chat/types/

## 架构概述

聊天域 TypeScript 契约。`../types.ts` 仅 re-export 本目录；调用方继续 `@/store/chat/types`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 核心 | 子模块 barrel | ✅ |
| `builtinTools.ts` | 核心 | GUI 可切换 builtin 产品 ID（不含 `answer_tool`；Fast Search 由服务端强制挂载） | ✅ |
| `sources.ts` | 核心 | 引用来源 / citation | ✅ |
| `sessionConfig.ts` | 核心 | Agent 与会话模式 | ✅ |
| `archiveRestore.ts` | 辅助 | 归档恢复 payload | ✅ |
| `progress.ts` | 核心 | ProgressItem 树 | ✅ |
| `contextMetrics.ts` | 辅助 | Cost / context budget | ✅ |
| `tokens.ts` | 辅助 | Token 用量快照 | ✅ |
| `artifacts.ts` | 核心 | 工件实体 | ✅ |
| `interactiveUi.ts` | 核心 | A2UI 组件 | ✅ |
| `toolApproval.ts` | 核心 | 工具审批 | ✅ |
| `agentStream/part1.ts` | 核心 | SSE 事件（前段） | ✅ |
| `agentStream/part2.ts` | 核心 | SSE 事件（中段） | ✅ |
| `agentStream/part3.ts` | 核心 | SSE 事件（末段） | ✅ |
| `agentStream/union.ts` | 核心 | `AgentStreamEvent` union | ✅ |
| `messages.ts` | 核心 | `Message` / 历史 / @mention | ✅ |
| `pendingGapRetry.ts` | 辅助 | `PendingGapRetry` 延迟重发契约类型 | ✅ |
| `chatState.ts` | 核心 | `ChatState` + actions | ✅ |

## 依赖

- `@/store/config/providerTypes` — 模型选择
- `@/components/features/chat-window/goals/GoalStatusCard` — `GoalStatusPayload.status`（`part2.ts`）

## 约束

- 单文件不超过 500 行；新增类型写入对应域文件。
- `messageStream/types.ts` 为本目录外的流 handler 专用类型，勿合并进此包。
