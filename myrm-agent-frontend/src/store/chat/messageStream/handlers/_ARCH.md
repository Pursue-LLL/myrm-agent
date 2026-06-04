# handlers/

## 架构概述

`AgentStreamEvent` 按事件域拆分的 SSE reducer 切片。由 `index.ts` 的 `STREAM_EVENT_HANDLERS` 顺序调用；共享依赖见 `handlerDeps.ts`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 核心 | 导出 `STREAM_EVENT_HANDLERS` 调用顺序 | ✅ |
| `handlerDeps.ts` | 辅助 | 切片共享 import（types、stores、helpers） | ✅ |
| `companionEvents.ts` | 核心 | mascot_xp、dag、catchup_snapshot | 见源码 |
| `rateLimitEvents.ts` | 核心 | rate_limit_updated / warning | 见源码 |
| `agentControlEvents.ts` | 核心 | ERROR、取消、澄清、Goal、审批等控制流 | 见源码 |
| `toolsProgressEvents.ts` | 核心 | TOOL_PROGRESS、TASKS_STEPS、进度项合并 | 见源码 |
| `statusStreamEvents.ts` | 核心 | STATUS、归档恢复、上下文溢出提示 | 见源码 |
| `subagentEvents.ts` | 核心 | SUBAGENT_* 子代理状态 | 见源码 |
| `fileDiffEvents.ts` | 核心 | FILE_DIFF、TOOL_IMAGE_OUTPUT、FILE_MUTATION_FAILED | 见源码 |
| `toolLifecycleEvents.ts` | 核心 | TOOL_START/END、审批请求与结果 | 见源码 |
| `routingMetaEvents.ts` | 核心 | ROUTING_DECISION、模型路由元数据 | 见源码 |
| `messageContentEvents.ts` | 核心 | REASONING、MESSAGE、MESSAGE_DELTA | 见源码 |
| `artifactEvents.ts` | 核心 | ARTIFACTS、UI_UPDATE | 见源码 |
| `captchaEvents.ts` | 核心 | CAPTCHA 进度展示 | 见源码 |
| `modelNotifyEvents.ts` | 核心 | MODEL_ESCALATED、降级通知 | 见源码 |
| `completionEvents.ts` | 核心 | MESSAGE_END、完成态、建议与自动保存 | 见源码 |

## 依赖

- `../streamContext.ts` — `StreamCtx`、`done()`
- `../types.ts`、`../streamHelpers.ts`、`../fileDiffMerge.ts`
- `@/store/*` — 门户、审批、配置等（经 `handlerDeps.ts`）

## 约束

- 单切片建议 ≤300 行；新增事件优先扩展现有域文件或新增 `*Events.ts` 并注册到 `index.ts`。
- 可变回合状态只改 `ctx.added` / `ctx.recievedMessage`，禁止对解构常量赋值。
