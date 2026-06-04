# lib/approval/

## 架构概述

工具审批（HITL）的前端决策与可视化上下文解析。与 `useToolApprovalStore` 队列、`createAISearchStream` resume 通道配合，将用户决策写回 Agent 流。

## 模块

| 文件 | 职责 |
| ---- | ---- |
| `visualApprovalContext.ts` | 从 inspector snapshot + toolInput 解析 BBox 高亮上下文 |
| `visualApprovalSurface.ts` | inline（聊天内嵌）vs modal（对话框）表面分区；batch 同 surface |
| `visualApprovalRenderState.ts` | loading / ready / unavailable 渲染态解析 |
| `approvalBulkGroups.ts` | bulk approve/reject 的分组（batchId / messageId） |
| `approvalDecision.ts` | resume decision payload 构建 |
| `resumeApprovalStream.ts` | 通过 SSE resume 恢复执行 |

## 依赖

- `@/store/useDesktopInspectorStore`、`@/store/useBrowserInspectorStore`：截图与 ref
- `@/hooks/useToolApprovalResolve`：React hook，编排单条与 bulk 决策
- `@/hooks/useVisualApprovalSnapshot`：pending visual 审批时自动 `fetchSnapshot`

## UI 入口

- `chat-window/VisualApprovalInlineSection.tsx`：桌面聊天 inline artifact
- `chat-window/approval/VisualApprovalRequestRenderer.tsx`：loading/ready/unavailable 三态渲染
- `chat-window/approval/VisualApprovalUnavailableCard.tsx`：snapshot 失败降级 + 重试
- `chat-window/VisualApprovalPendingCard.tsx`：snapshot loading 占位
- `chat-window/VisualApprovalArtifactCard.tsx`：截图 + BBox + 审批操作
- `chat-window/ToolApprovalDialog.tsx`：modal 审批（非 visual / handover）
- `chat-window/MobileStatusBoard.tsx`：移动端复用同一 surface 规则
