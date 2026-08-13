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
| `agentControlEvents.ts` | 核心 | ERROR、取消、澄清、Goal、审批；ERROR/CANCEL 后 `scheduleFlushPendingGapRetry`；ERROR/AGENT_CANCELLED/CONTEXT_OVERFLOW_RESET 三条终止路径经 [lib/inspector 共享 `releaseTurnInspectorControls`](../../../../lib/inspector/_ARCH.md) 归还 desktop + browser inspector 控制状态（均无 MESSAGE_END 跟随） | ✅ |
| `toolsProgressEvents.ts` | 核心 | TOOL_PROGRESS、TASKS_STEPS、CLARIFICATION_REQUIRED（unwrap `{type,form}`；`source=deep_research` 或 `actionMode=deep_research` → `isResumeMode=false`）、进度项合并 | ✅ |
| `statusStreamEvents.ts` | 核心 | STATUS、归档恢复、上下文溢出提示；`waiting_for_turn_clear` 移除项目锁等待 step（`waiting_for_turn` 由 `statusStreamProgressSteps` 消费） | ✅ |
| `statusStreamProgressSteps.ts` | 辅助 | STATUS `progress.step_key` 分支与 toast（含 stream recovery；`model_failover` 与 `modelNotifyEvents` MODEL_FAILOVER 双通道按 `model_failover*` 前缀去重为单 step；**restart 协议**：`model_failover`/`safety_fallback_active` 或 `data.restart === true` 的 STATUS（transient_retry/empty_response_recovery/tool_call_retry/vision_fallback_recovery/media_rejected_recovery/context_compaction 等）到达时经 `discardStreamedDraft`（ctx 级重置 chunk 缓冲 + `scheduler.cancel()` 丢弃旧渲染闭包）+ `clearAssistantDraft`（message 级清 content/reasoning 废稿与 reasoning 计时）清稿，与 MODEL_FAILOVER SSE 幂等；`empty_response_recovery`/`context_truncation` 多次重试去重为单 step（同 key 更新而非追加）；早于 MESSAGE 到达时 `data.restart === true` 或 early 恢复列表命中均创建 assistant 占位消息承接 progress step；`model_failover_unconfigured` → `/settings/defaultModel`；`safety_fallback_unconfigured` → `/settings/agents#loadout`；`turn_prewarm_*` · `wiki_knowledge_lane`；`waiting_for_turn` 项目锁等待 step（early recovery 占位 + i18n 标题）） | ✅ |
| `statusStreamPhaseData.ts` | 辅助 | STATUS `data.phase` 多阶段 payload 处理 | ✅ |
| `subagentEvents.ts` | 核心 | SUBAGENT_* 子代理状态与进度 | ✅ |
| `fileDiffEvents.ts` | 核心 | FILE_DIFF、TOOL_IMAGE_OUTPUT、BROWSER/DESKTOP_VIEW_UPDATE（browser/desktop SSE 写 `sourceChatId`、不 openPanel、`markTurnEngaged`）、DESKTOP_CONTROL_APPROVAL（前台 chat 匹配时 `setDesktopActive(true)` + openPanel）、BROWSER_TAKEOVER_*（`setLoading(false)`；pet waiting 由 PetOverlay store SSOT；`is_managed=false` 自动签发 `browser_takeover` pair token 并写入 `liveAssistUrl`；managed POST 失败 toast） | ✅ |
| `takeoverVncMessages.ts` | 辅助 | managed VNC takeover POST 失败 toast 文案（与 locales billing.vnc.takeoverVncOpenFailed 同步） | ✅ |
| `toolLifecycleEvents.ts` | 核心 | TOOL_START/END、审批请求与结果；`browser_*` TOOL_START 在前台 chat 匹配时 openPanel（任意 chat 均 `setBrowserActive` + `markTurnEngaged`）；`desktop_*` TOOL_END REST re-fetch 仅前台 chat 匹配时执行；`kanban_add_task`/`cron_manage` 成功写入 message metadata；`kanban_add_task` 软错误 JSON 标记 progress error | ✅ |
| `memoryBriefEvents.ts` | 核心 | `memory_brief` 发送前记忆简报事件：创建/更新 assistant 占位消息并挂载简报快照 | ✅ |
| `routingMetaEvents.ts` | 核心 | ROUTING_DECISION、模型路由元数据 | ✅ |
| `messageContentEvents.ts` | 核心 | REASONING、MESSAGE、MESSAGE_DELTA 文本流合并；当 `personalSettings.reasoningDisplayMode=off` 时直接丢弃 reasoning chunk 以减少前端内存占用；clarify metadata 合并时保留既有 `isResumeMode`/form | ✅ |
| `artifactEvents.ts` | 核心 | ARTIFACTS、UI_UPDATE（`ui_artifact` 追加；`data_update` 按 `surface_id` 跨 assistant 消息 merge data） | ✅ |
| `captchaEvents.ts` | 核心 | CAPTCHA 进度展示与状态更新 | ✅ |
| `sessionRecordingEvents.ts` | 核心 | SESSION_RECORDING 视频回放元数据 | ✅ |
| `modelNotifyEvents.ts` | 核心 | MODEL_ESCALATED、MODEL_FAILOVER、MODEL_RECOVERY（toast 经 `modelNotifyToastKey` 6-locale i18n SSOT；MODEL_FAILOVER progress step 与 STATUS 通道去重；**restart 协议**：MODEL_FAILOVER 到达时经 `discardStreamedDraft`（ctx 级）+ `clearAssistantDraft`（message 级）清空已流式废稿并丢弃旧渲染闭包——fallback 从头重跑，避免旧废稿拼接完整回答；MODEL_ESCALATED payload `restart:true` 时同样清空废稿——升级模型重跑本轮） | ✅ |
| `modelNotifyToastKey.ts` | 辅助 | MODEL_ESCALATED/FAILOVER/RECOVERY → `progressSteps.*` i18n key 映射（含 `auth_permanent`/`session_expired` → `model_failover_auth`、`safety_block` → `safety_fallback_active`，与 STATUS 通道派生一致） | ✅ |
| `completionEvents.ts` | 核心 | MESSAGE_END、完成态、建议与自动保存；FILE_MUTATION_FAILED / WORKSPACE_MERGE_FAILED 持久化到 message；持久化 `execution_lane` / wiki lane metrics；回填 `memory_brief_snapshot_id` + `memory_brief_status`；`flushPendingGapRetry` 于 loading 落盘后自动重发；MESSAGE_END 与 GOAL_STATUS `budget_limited` 熔断（无终止事件跟随）两条路径经 [lib/inspector 共享 `releaseTurnInspectorControls`](../../../../lib/inspector/_ARCH.md) 归还 desktop + browser inspector 控制状态 | ✅ |
| `gapEvents.ts` | 核心 | CAPABILITY_GAP / SKILL_GAP SSE → toast 开启并重发；`surface_unavailable` → info-only toast；`web_search` + `not_configured|unreachable` → `webSearchConfigGap` SSOT toast；`migration_readiness_critical|warning` → issue-aware settings CTA toast | ✅ |
| `renderUiSurfaceUnavailableMessage.ts` | 辅助 | `capability_gap` surface_unavailable fallback 文案（与 `agent.configPanel.renderUiWebOnlyHint` 同步） | ✅ |
| `__tests__/gapEvents.test.ts` | 测试 | gap handler 回归（含 web_search config gap CTA、loading 延迟重发） | ✅ |
| `__tests__/completionEvents.pendingGapRetry.test.ts` | 测试 | MESSAGE_END 后 flush pending gap | ✅ |
| `__tests__/completionEvents.workspaceMerge.test.ts` | 测试 | WORKSPACE_MERGE_FAILED → message workspaceMergeFailures/count/truncated | ✅ |
| `__tests__/agentControlEvents.pendingGapRetry.test.ts` | 测试 | ERROR/CANCEL 后 flush pending gap | ✅ |
| `__tests__/agentControlEvents.clearActivePlan.test.ts` | 测试 | ERROR/AGENT_CANCELLED 清 activePlan；三条终止路径（ERROR/AGENT_CANCELLED/CONTEXT_OVERFLOW_RESET）经共享 helper 释放 inspector 控制状态；非终止事件（STEERING）不释放 | ✅ |
| `__tests__/fileDiffEvents.takeover.test.ts` | 测试 | BROWSER_TAKEOVER is_managed 分支 + setLoading(false)（local 跳过 VNC 并校验签名接管链接生成；managed POST） | ✅ |
| `__tests__/fileDiffEvents.browserViewUpdate.test.ts` | 测试 | BROWSER_VIEW_UPDATE：sourceChatId 写入、不 openPanel、markTurnEngaged | ✅ |
| `__tests__/fileDiffEvents.desktopViewUpdate.test.ts` | 测试 | DESKTOP_VIEW_UPDATE：sourceChatId 写入 | ✅ |
| `__tests__/fileDiffEvents.desktopControlApproval.test.ts` | 测试 | DESKTOP_CONTROL_APPROVAL：前台 chat 匹配时 setDesktopActive + openPanel | ✅ |
| `__tests__/toolLifecycleEvents.browserInspector.test.ts` | 测试 | browser_* TOOL_START 前台 chat 匹配时才 openPanel；任意 browser_* TOOL_START markTurnEngaged | ✅ |
| `__tests__/toolLifecycleEvents.desktopInspector.test.ts` | 测试 | desktop_* TOOL_END REST re-fetch 仅前台 chat 匹配时执行；desktop_* TOOL_START markTurnEngaged | ✅ |
| `__tests__/completionEvents.desktopTeardown.test.ts` | 测试 | MESSAGE_END → 经共享 helper 释放 desktop + browser releaseTurnEngagement；GOAL_STATUS `budget_limited` 熔断同样释放；非 MESSAGE_END/非熔断不释放 | ✅ |
| `__tests__/statusStreamProgressSteps.allowedToolsRecovery.test.ts` | 测试 | stream recovery + `allowed_tools_rejected_recovery` progress step 白名单 | ✅ |
| `__tests__/statusStreamProgressSteps.modelFailoverKey.test.ts` | 测试 | `model_failover` displayKey 按 `error_kind` 派生；`model_failover_unconfigured` step 白名单；restart 协议（`data.restart===true` 清空草稿 + `scheduler.cancel()`），含 `empty_response_recovery`/`tool_call_retry`/`vision_fallback_recovery`/`media_rejected_recovery` 白名单、清稿与 early 占位 | ✅ |
| `__tests__/statusStreamEvents.waitingForTurn.test.ts` | 测试 | `waiting_for_turn` 白名单/占位/step 追加 + `waiting_for_turn_clear` step 移除 | ✅ |
| `tests/e2e/test_model_failover_chrome_e2e.py` | Chrome E2E | primary key 故意失效 → base fallback MiniMax → WebUI progress step + assistant OK（PRIVATE + MCP mux） | ✅ |
| `__tests__/modelNotifyToastKey.test.ts` | 测试 | modelNotify toast → progressSteps i18n key 映射 | ✅ |

## 依赖

- `../streamContext.ts` — `StreamCtx`、`done()`
- `../types.ts`、`../streamHelpers.ts`、`../fileDiffMerge.ts`
- `@/store/*` — 门户、审批、配置等（经 `handlerDeps.ts`）

## 约束

- 单切片建议 ≤300 行；新增事件优先扩展现有域文件或新增 `*Events.ts` 并注册到 `index.ts`。
- 可变回合状态只改 `ctx.added` / `ctx.recievedMessage`，禁止对解构常量赋值。
