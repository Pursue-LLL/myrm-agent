# chat/

## 架构概述

会话状态、SSE 流式 reducer、发送请求与类型契约。侧边栏 navigation snapshot + multi-pane `resolvePaneSnapshotBase`（含 per-chat `activeMoaPresetId`）实现 instant re-entry。

## 子模块

| 路径 | 职责 |
|------|------|
| `types/` | `AgentStreamEvent`、`Message`、`ChatState` 等 |
| `messageStream/` | SSE dispatcher + `handlers/*` |
| `schema.ts` / `knownSseEventTypes.ts` | SSE 入站校验与 harness 对齐 |
| `streamConsumer.ts` | 读 SSE 行 → `parseSseEnvelope` → reducer；导出 `isAgentBusySseEvent` / `AgentBusyError` 供 HITL resume（`resumeApprovalStream`、`resumePlanConfirmStream`）复用；`executeStreamWithRetry` 网络重试保留同一 `requestMessageId`；**agent-stream `res.ok` 后 `finalizeMigrationBoundProjectHandoff`（consume migration bound project + sidebar sync）**；busy 检测：**HTTP 409** 或 **SSE `{type:error, error_type:AgentBusyError}`**；multiplex 下 POST 若仍为 `text/event-stream`（early terminal：busy/risk 等）则**直接 consume POST**，不 drain 丢包；JSON accepted 仍走 workspace bridge；busy fail-fast 不重试（由 `useMessageInput` requeue）；`StreamInterruptedError` 走 attach/loadMessages 而非 blind 重 POST；支持 `e2ee_frame` 解密与 multiplex `accepted.message_id` 握手复用；按发送标记在首个有效业务 SSE 帧到达后补记 chat `query_submitted(success)`；携带并透传 `turnCapabilityTelemetry` 给 request 组装层；流结束 `finally` 调用 `recoverPendingApprovals()` 补全 missed HITL |
| `messageRequest.ts` | 组装请求并启动流（含 Smart Updater 路由、kanban 发送前看板 guard）；Agent 模式携带 `active_moa_preset_id`（会话 MoA preset）；发送前统一归一化 `mcp_cfg` transport/keepalive 语义；fast/deep 发送前 search guard block；agent 模式 web_search 未配置由 SSE preflight gap 通知（无 client 重复 toast）；`resumeValue` 存在时跳过 loading/isProcessing 守卫以支持 browser takeover Done/Skip resume；新 send 时 clear pending gap；统一携带 `reasoning_display_mode`（off/collapsed/inline）到 API；当有单轮 Skill/MCP 覆写时附带 `turn_capability_telemetry`（source + effective counts）供服务端写入终态埋点 |
| `pendingGapRetry.ts` | entitlement gap 延迟重发：pending 状态 + flush + schedule |
| `multimodalBuilder.ts` | 附件→multimodal 消息构建（PDF/图片/视频/摄像头/文本），视觉内容始终发送由后端 VisionFallback 路由 |
| `messageManagement.ts` | 会话初始化（LRU 优先 + pane 流式 merge）、silent refresh 保留 session config、`LoadMessagesOptions`；hydrate 时 `normalizeHydratedClarification` 恢复 pending clarify，并将历史 `metadata.reasoning_content` 回填到 `message.reasoning` 保证回放一致性 |
| `clarificationState.ts` | pending clarify 选择器（倒序扫描 assistant，跳过无 pending 的较新消息）+ DB hydrate 归一化（`answered`/`isResumeMode`） |
| `chatNavigationSnapshotCache.ts` | 侧边栏 LRU snapshot（20 条，跳过 incognito）；含 agentConfig/actionMode/selectedModels/contextBranches/contextPinnedFiles 及 load error 态；`resolvePaneSnapshotBase` 与 LRU 共用 session 字段 |
| `chatSessionConfig.ts` | Session 字段 SSOT（`activeMoaPresetId` 等）；LRU / pane / background SmartUpdater 三处复用 |
| `moaPresetStorage.ts` | per-chat `activeMoaPresetId` localStorage + `resolveHydratedMoaPresetId`（DB 优先 hydrate；incognito 不读写） |
| `useChatStore.ts`（根 store） | `refreshCompactionState`：压缩 SSE 后并行 refresh summary/branches/pins（`Promise.allSettled`，detail 失败不阻断 metadata） |
| `messageUtils.ts` | assistant 消息索引、`findUiArtifactLocation`（`data_update` 跨回合 surface 定位） |
| `__tests__/` | 请求组装、SSE schema、stream consumer 异常恢复与 handler reducer 回归测试 |
| `goals/` | Goal 队列与 Plan 步骤 store | [_ARCH.md](goals/_ARCH.md) |

## 依赖

- `@/services/chat` — HTTP/SSE API
- `@/store/useWorkspaceStore` — 多 pane workspace snapshot
- `myrm-agent-harness` `AgentEventType`（通过 `knownSseEventTypes` 清单对齐）
