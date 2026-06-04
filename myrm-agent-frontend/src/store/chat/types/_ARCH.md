# chat/types/

## 架构概述

聊天域 TypeScript 契约。`../types.ts` 仅 re-export 本目录，调用方路径 `@/store/chat/types` 不变。

## 模块

| 文件 | 职责 |
|------|------|
| `builtinTools.ts` | 内置工具 ID 常量 |
| `sources.ts` | 引用来源、记忆 citation、文件变更失败 |
| `sessionConfig.ts` | ActionMode、AgentConfig、模型选择 |
| `archiveRestore.ts` | 归档恢复 payload |
| `progress.ts` | ProgressItem、RecoveryAction |
| `contextMetrics.ts` | CostStatus、ContextBudget |
| `tokens.ts` | TokenUsage、TokenEconomicsSnapshot |
| `artifacts.ts` / `interactiveUi.ts` | 工件与 A2UI |
| `toolApproval.ts` | 工具审批与 ToolCallInfo |
| `agentStream/` | SSE 事件（part1–3 + union） |
| `messages.ts` | Message、File、ChatHistory |
| `chatState.ts` | ChatState 接口 |

## 约束

- 新类型按域加入对应文件，禁止再膨胀单文件 >500 行。
- `agentStream/part2.ts` 引用 `GoalStatusCard` 类型，保持与 goals UI 同步。
