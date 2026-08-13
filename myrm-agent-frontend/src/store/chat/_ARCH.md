# chat/

## 架构概述

会话状态、SSE 流式 reducer、发送请求与类型契约。侧边栏 navigation snapshot + multi-pane `resolvePaneSnapshotBase`（含 per-chat `activeMoaPresetId`）实现 instant re-entry。

## 子模块

| 路径 | 职责 |
|------|------|
| `types/` | `AgentStreamEvent`、`Message`、`ChatState` 等 |
| `messageStream/` | SSE dispatcher + `handlers/*` |
| `schema.ts` / `knownSseEventTypes.ts` | SSE 入站校验与 harness 对齐 |
| `streamConsumer.ts` | 读 SSE 行 → `parseSseEnvelope` → reducer；导出 `isAgentBusySseEvent` / `AgentBusyError` 供 HITL resume（`resumeApprovalStream`、`resumePlanConfirmStream`）复用；`executeStreamWithRetry` 网络重试保留同一 `requestMessageId`；**agent-stream `res.ok` 后** `clearPendingWorkflowTemplate`（失败保留 armed 态）与 `finalizeMigrationBoundProjectHandoff`；busy 检测：**HTTP 409** 或 **SSE `{type:error, error_type:AgentBusyError}`**；multiplex 下 POST 若仍为 `text/event-stream`（early terminal：busy/risk 等）则**直接 consume POST**，不 drain 丢包；JSON accepted 仍走 workspace bridge；busy fail-fast 不重试（由 `useMessageInput` requeue）；`StreamInterruptedError` 走 attach/loadMessages 而非 blind 重 POST，其中 attach 返回 false（任务已结束）时按归属 chatId 无条件 `releaseTurnInspectorControls(chatId)` 释放 turn 期间 desktop/browser Inspector 控制权（不依赖最终状态拉取成败），与 `loadMessages` 清 loading 共同构成同路径收尾；支持 `e2ee_frame` 解密与 multiplex `accepted.message_id` 握手复用；按发送标记在首个有效业务 SSE 帧到达后补记 chat `query_submitted(success)`；携带并透传 `turnCapabilityTelemetry` 给 request 组装层；流结束 `finally` 调用 `recoverPendingApprovals()` 补全 missed HITL |
| `messageRequest.ts` | 组装请求并启动流（含 Smart Updater 路由、kanban 发送前看板 guard）；**user 消息在 store 中以 `requestMessageId`（`r-` 前缀）作为唯一 `messageId`**——与 API 请求 ID 同源，保证回退/revert/文件快照 API 按该 ID 检索用户消息；Agent 模式携带 `active_moa_preset_id`（会话 MoA preset）与**始终显式发送 `security_preset`**（含 hitl，前端负责初始化会话预设）；发送前统一归一化 `mcp_cfg` transport/keepalive 语义；fast/deep 发送前 search guard block；agent 模式 web_search 未配置由 SSE preflight gap 通知（无 client 重复 toast）；`resumeValue` 存在时跳过 loading/isProcessing 守卫以支持 browser takeover Done/Skip resume；新 send 时 clear pending gap；统一携带 `reasoning_display_mode`（off/collapsed/inline）到 API；当有单轮 Skill/MCP 覆写时附带 `turn_capability_telemetry`（source + effective counts）供服务端写入终态埋点 |
| `pendingGapRetry.ts` | entitlement gap 延迟重发：pending 状态 + flush + schedule |
|| `securityPreset.ts` | 会话安全预设 SSOT：`normalizeSecurityPreset` 归一化（非法/缺省回落 hitl）、`isYoloEnabled`/`disableYolo` 全局 YOLO 原语、`disarmYoloForPreset` 在选择非 HITL 预设（accept_edits/explore）时关闭 YOLO、`resolvePresetWithYoloMutex` 选择器互斥决策（YOLO 开启时任何选择含点击当前项都先关闭 YOLO）、`resolvePresetWithYoloMutexEnsured` 选择器入口（决策前 `ensureKeyLoaded('securityConfig')`，渐进加载下避免 YOLO 状态误读为关闭）、`enforceSecurityPresetYoloMutex` 配置就绪/变更后的互斥重放（覆盖 securityConfig 异步加载期间已完成 Agent 绑定导致的 YOLO 残留竞态）；手动选择、Agent 默认预设初始化与进入聊天重置三入口共用同一规则 |
| `multimodalBuilder.ts` | 附件→multimodal 消息构建（PDF/图片/视频/摄像头/文本），视觉内容始终发送由后端 VisionFallback 路由 |
| `messageManagement.ts` | 会话初始化（LRU 优先 + pane 流式 merge）、silent refresh 保留 session config、`LoadMessagesOptions`；进入聊天时按恢复的 agentConfig 默认重置 `securityPreset`（无默认回落 hitl，fail-closed）；hydrate 时 `normalizeHydratedClarification` 恢复 pending clarify，并将历史 `metadata.reasoning_content` 回填到 `message.reasoning` 保证回放一致性；同时从 `metadata.request_message_id` 恢复 `message.requestMessageId`——assistant 消息 DB 主键为 UUID、实时流中其 messageId 即 `r-` 请求 ID，此字段让刷新后文件回退等按回合定位的 API 仍能拿到 `r-` 前缀 ID |
| `clarificationState.ts` | pending clarify 选择器（倒序扫描 assistant，跳过无 pending 的较新消息）+ DB hydrate 归一化（`answered`/`isResumeMode`） |
| `chatNavigationSnapshotCache.ts` | 侧边栏 LRU snapshot（20 条，跳过 incognito）；含 agentConfig/actionMode/selectedModels/contextBranches/contextPinnedFiles 及 load error 态；`resolvePaneSnapshotBase` 与 LRU 共用 session 字段 |
| `chatSessionConfig.ts` | Session 字段 SSOT（`activeMoaPresetId` 等）；LRU / pane / background SmartUpdater 三处复用 |
| `moaPresetStorage.ts` | per-chat localStorage + DB PATCH（`persistMoaPresetToServer` fail-visible rollback）+ `resolveHydratedMoaPresetId` |
| `useChatStore.ts`（根 store） | `refreshCompactionState`：压缩 SSE 后并行 refresh summary/branches/pins（`Promise.allSettled`，detail 失败不阻断 metadata）；`setAgentConfig` 绑定/切换 Agent 时重置 `securityPreset`（无默认回落 hitl，fail-closed） |
| `messageUtils.ts` | assistant 消息索引、`findUiArtifactLocation`（`data_update` 跨回合 surface 定位）、`removeWaitingForTurnStep`（取消时同步清除 `waiting_for_turn` 进度步骤，防 UI 残留卡死） |
| `useSubagentStore.ts` | 子代理运行时状态 store（`SubagentNode`/`SubagentStatus` 类型、SSE 树更新、teammate 消息、预算 metadata `budget`/`token_usage`、overtime/stale 告警、独立验证 `verification`（`SubagentVerification`）、fission 批次汇总 `fissionBatch`/`setFissionBatch` 与拓扑 `fissionTopology`/`setFissionTopology`；`setNodes` 对已终态（`TERMINAL_SUBAGENT_STATUSES`：cancelled/completed/failed/timed_out/cancelled_by_budget/interrupted）节点提供防回退保护，避免迟到 SSE/API 的 running 快照覆盖回退；挂 `window.__myrmSubagentStore` 供 chrome E2E 注入种子数据） |
| `adaptiveScheduler.ts` | 自适应调度器：按文本长度动态调度任务（打字机流控 timer，支持 flush） |
| `archiveRestoreActions.ts` | 归档恢复动作 SSOT：block/result payload 解析归一化 + 构建（每请求上限 `MAX_ARCHIVE_RESTORE_ACTIONS_PER_REQUEST`） |
| `chatHistoryBuilder.ts` | 聊天历史构建（`buildSimpleChatHistory` 等） |
| `cliAgentMessageHandler.ts` | CLI Agent 模式：`CLIAgentState`/`CLIAgentActions` 类型 + `isCLIAgentMode` + `sendCLIAgentMessage` |
| `directoryRequestState.ts` | `normalizeHydratedDirectoryRequest`：目录请求状态归一化（DB hydrate 恢复） |
| `memoryCitationUtils.ts` | 记忆引用工具：`isMemoryRecallToolName` 识别 + `normalizeCitedMemoryReferences`/`mergeCitedMemoryReferences` |
| `messageStreamHandler.ts` | 门面：chat 流消费的稳定导入路径（re-export `handleMessageStream` 与流类型） |
| `multiplexChunkBridge.ts` | multiplex 分块桥：`createMultiplexChunkBridge` 缓冲早期 chunk 直至 consumer attach + `createMultiplexReadableStream`；terminal chunk 检测 |
| `streamRequestMessageId.ts` | `generateStreamRequestMessageId`：SSE 流请求 ID 生成（时间戳 + 微秒 + 随机字节） |
| `types.ts` | 门面：re-export `types/` 子目录（`export * from './types/index'`） |
| `__tests__/` | 请求组装、SSE schema、stream consumer 异常恢复、handler reducer 回归测试；安全预设生命周期测试（`normalizeSecurityPreset`/`disarmYoloForPreset`/`isYoloEnabled`/`disableYolo`/`resolvePresetWithYoloMutex` 纯函数 + initializeChat 快照重置） |
| `goals/` | Goal 队列与 Plan 步骤 store | [_ARCH.md](goals/_ARCH.md) |

## 依赖

- `@/services/chat` — HTTP/SSE API
- `@/store/useWorkspaceStore` — 多 pane workspace snapshot
- `myrm-agent-harness` `AgentEventType`（通过 `knownSseEventTypes` 清单对齐）
