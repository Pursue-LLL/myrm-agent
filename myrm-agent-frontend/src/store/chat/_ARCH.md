# chat/

## 架构概述

会话状态、SSE 流式 reducer、发送请求与类型契约。侧边栏导航切换使用 LRU navigation snapshot 缓存实现 instant re-entry。

## 子模块

| 路径 | 职责 |
|------|------|
| `types/` | `AgentStreamEvent`、`Message`、`ChatState` 等 |
| `messageStream/` | SSE dispatcher + `handlers/*` |
| `schema.ts` / `knownSseEventTypes.ts` | SSE 入站校验与 harness 对齐 |
| `streamConsumer.ts` | 读 SSE 行 → `parseSseEnvelope` → reducer |
| `messageRequest.ts` | 组装请求并启动流（含 Smart Updater 路由、kanban 发送前看板 guard）；新 send 时 clear pending gap |
| `pendingGapRetry.ts` | entitlement gap 延迟重发：pending 状态 + flush + schedule |
| `multimodalBuilder.ts` | 附件→multimodal 消息构建（PDF/图片/视频/摄像头/文本），视觉内容始终发送由后端 VisionFallback 路由 |
| `messageManagement.ts` | 会话初始化（LRU 优先 + pane 流式 merge）、silent refresh 保留 session config、`LoadMessagesOptions` |
| `chatNavigationSnapshotCache.ts` | 侧边栏 LRU snapshot（20 条，跳过 incognito）；含 agentConfig/actionMode/selectedModels |
| `goals/` | Goal 队列与 Plan 步骤 store | [_ARCH.md](goals/_ARCH.md) |

## 依赖

- `@/services/chat` — HTTP/SSE API
- `@/store/useWorkspaceStore` — 多 pane workspace snapshot
- `myrm-agent-harness` `AgentEventType`（通过 `knownSseEventTypes` 清单对齐）
