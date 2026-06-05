# lib/approval/

## 架构概述

工具审批（HITL）的前端决策与可视化上下文解析。与 `useToolApprovalStore` 队列、`createAISearchStream` resume 通道配合，将用户决策写回 Agent 流。

## 模块

| 文件 | 职责 |
| ---- | ---- |
| `visualApprovalContext.ts` | 从 inspector snapshot + toolInput 解析 BBox 高亮上下文；`mapScreenSpaceBBoxToImageSpace` 供 inline 红框 |
| `visualApprovalSurface.ts` | inline（聊天内嵌）vs modal（对话框）表面分区；batch 同 surface |
| `visualApprovalRenderState.ts` | loading / ready / unavailable 渲染态解析 |
| `visualApprovalOsOverlay.ts` | Tauri OS overlay IPC payload + show/hide bridge（screen/image 双坐标模式） |
| `resolveDesktopOverlayTarget.ts` | 最早过期 desktop ready 态 + AttentionBar 主 request 共用选择 |
| `approvalBulkGroups.ts` | bulk approve/reject 的分组（batchId / messageId） |
| `approvalDecision.ts` | resume decision payload 构建 |
| `buildToolApprovalRequest.ts` | SSE/WS actionRequest → ToolApprovalRequest（含 commandSpans/risks/workspaceRoot） |
| `shellCommandDisplay.ts` | shell 工具名识别、命令文本提取、span 校验、zipSpansWithRisks |
| `resumeApprovalStream.ts` | 通过 SSE resume 恢复执行 |

## 依赖

- `@/store/useDesktopInspectorStore`：截图与 ref（含 `screenWidth/screenHeight/dpiScale`）
- `@/hooks/useToolApprovalResolve`：React hook，编排单条与 bulk 决策
- `@/hooks/useVisualApprovalSnapshot`：pending visual 审批时自动 `fetchSnapshot`
- `@/hooks/useVisualApprovalOsOverlay`：Tauri 原生 OS 红框 overlay 生命周期

## UI 入口

- `chat-window/VisualApprovalInlineSection.tsx`：桌面聊天 inline artifact
- `chat-window/VisualApprovalOsOverlaySync.tsx`：Tauri OS overlay 生命周期同步
- `chat-window/approval/VisualApprovalRequestRenderer.tsx`：loading/ready/unavailable 三态渲染
- `chat-window/approval/VisualApprovalUnavailableCard.tsx`：snapshot 失败降级 + 重试
- `chat-window/approval/VisualApprovalAttentionBar.tsx`：滚动区外 pending 可达条（Chat 输入框上）
- `chat-window/VisualApprovalPendingCard.tsx`：snapshot loading 占位
- `chat-window/VisualApprovalArtifactCard.tsx`：截图 + BBox + 审批操作
- `chat-window/ToolApprovalDialog.tsx`：modal 审批（非 visual / handover）
- `chat-window/approval/ShellCommandDisplay.tsx`：shell 命令终端展示 + pipeline span 高亮
- `components/approval/PolymorphicApprovalCard.tsx`：SubAgent 批量审批（复用 ShellCommandDisplay）
- `chat-window/MobileStatusBoard.tsx`：移动端复用同一 surface 规则
