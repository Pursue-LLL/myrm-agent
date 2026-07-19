# handlers/

## 架构概述

`AgentStreamEvent` 按事件域拆分的 SSE reducer 切片。由 `index.ts` 的 `STREAM_EVENT_HANDLERS` 顺序调用；共享依赖见 `handlerDeps.ts`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 核心 | 导出 `STREAM_EVENT_HANDLERS` 调用顺序 | ✅ |
| `handlerDeps.ts` | 辅助 | 切片共享 import（types、stores、helpers） | ✅ |
| `companionEvents.ts` | 核心 | `mascot_xp`、`dag`、`catchup_snapshot` 桌宠/Companion 事件 | ✅ |
| `rateLimitEvents.ts` | 核心 | `rate_limit_updated` / warning 配额告警合并 | ✅ |
| `agentControlEvents.ts` | 核心 | ERROR、取消、澄清、Goal、审批；ERROR/CANCEL 后 `scheduleFlushPendingGapRetry` | ✅ |
| `toolsProgressEvents.ts` | 核心 | TOOL_PROGRESS、TASKS_STEPS、CLARIFICATION_REQUIRED（unwrap `{type,form}` → ClarificationInput）、进度项合并 | ✅ |
| `statusStreamEvents.ts` | 核心 | STATUS、归档恢复、上下文溢出提示 | ✅ |
| `statusStreamProgressSteps.ts` | 辅助 | STATUS `progress.step_key` 分支与 toast | ✅ |
| `statusStreamPhaseData.ts` | 辅助 | STATUS `data.phase` 多阶段 payload 处理 | ✅ |
| `subagentEvents.ts` | 核心 | SUBAGENT_* 子代理状态与进度 | ✅ |
| `fileDiffEvents.ts` | 核心 | FILE_DIFF、TOOL_IMAGE_OUTPUT、FILE_MUTATION_FAILED、BROWSER_TAKEOVER_*（`is_managed=false` 跳过 VNC POST；managed POST 失败 toast） | ✅ |
| `takeoverVncMessages.ts` | 辅助 | managed VNC takeover POST 失败 toast 文案（与 locales billing.vnc.takeoverVncOpenFailed 同步） | ✅ |
| `toolLifecycleEvents.ts` | 核心 | TOOL_START/END、审批请求与结果 | ✅ |
| `memoryBriefEvents.ts` | 核心 | `memory_brief` 发送前记忆简报事件：创建/更新 assistant 占位消息并挂载简报快照 | ✅ |
| `routingMetaEvents.ts` | 核心 | ROUTING_DECISION、模型路由元数据 | ✅ |
| `messageContentEvents.ts` | 核心 | REASONING、MESSAGE、MESSAGE_DELTA 文本流合并 | ✅ |
| `artifactEvents.ts` | 核心 | ARTIFACTS、UI_UPDATE（`ui_artifact` 追加、`data_update` 合并 data） | ✅ |
| `captchaEvents.ts` | 核心 | CAPTCHA 进度展示与状态更新 | ✅ |
| `sessionRecordingEvents.ts` | 核心 | SESSION_RECORDING 视频回放元数据 | ✅ |
| `modelNotifyEvents.ts` | 核心 | MODEL_ESCALATED、降级/切换通知 | ✅ |
| `completionEvents.ts` | 核心 | MESSAGE_END、完成态、建议与自动保存；回填 `memory_brief_snapshot_id` + `memory_brief_status`；`flushPendingGapRetry` 于 loading 落盘后自动重发 | ✅ |
| `gapEvents.ts` | 核心 | CAPABILITY_GAP / SKILL_GAP SSE → toast 开启并重发；`pendingGapRetry` 在 stream 进行中延迟重发 | ✅ |
| `__tests__/gapEvents.test.ts` | 测试 | gap handler 回归（含 loading 延迟重发） | ✅ |
| `__tests__/completionEvents.pendingGapRetry.test.ts` | 测试 | MESSAGE_END 后 flush pending gap | ✅ |
| `__tests__/agentControlEvents.pendingGapRetry.test.ts` | 测试 | ERROR/CANCEL 后 flush pending gap | ✅ |
| `__tests__/fileDiffEvents.takeover.test.ts` | 测试 | BROWSER_TAKEOVER is_managed 分支（local 跳过 VNC；managed POST） | ✅ |

## 依赖

- `../streamContext.ts` — `StreamCtx`、`done()`
- `../types.ts`、`../streamHelpers.ts`、`../fileDiffMerge.ts`
- `@/store/*` — 门户、审批、配置等（经 `handlerDeps.ts`）

## 约束

- 单切片建议 ≤300 行；新增事件优先扩展现有域文件或新增 `*Events.ts` 并注册到 `index.ts`。
- 可变回合状态只改 `ctx.added` / `ctx.recievedMessage`，禁止对解构常量赋值。
