# chat-window/

## 架构概述

主对话窗口：消息列表、输入框、工具审批、Agent 配置、子代理与 Goal 控制面。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentInfoBanner.tsx` | 组件/模块 | 见源码 | 见源码 |
| `AgentWorkMap.tsx` | 组件/模块 | 见源码 | 见源码 |
| `BudgetBadge.tsx` | 组件/模块 | 见源码 | 见源码 |
| `Chat.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ChatWindow.tsx` | 组件/模块 | 见源码 | 见源码 |
| `CompactedSummaryView.tsx` | 组件/模块 | 见源码 | 见源码 |
| `CompetitorMigrationBanner.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ConversationJumpBar.tsx` | 组件/模块 | 见源码 | 见源码 |
| `DeleteChat.tsx` | 组件/模块 | 见源码 | 见源码 |
| `EmptyChat.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ForkButton.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ForkDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `LifeStatusCapsule.tsx` | 组件/模块 | 见源码 | 见源码 |
| `LinkDetectionDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `LocalCapabilitiesBanner.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MessageInput.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MessageListSkeleton.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MobileActionSheet.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MobileStatusBoard.tsx` | 组件/模块 | 见源码 | 见源码 |
| `Navbar.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ParentChatLink.tsx` | 组件/模块 | 见源码 | 见源码 |
| `QuoteCard.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ReferenceMentionPopover.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SamplePrompts.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SessionTrashPanel.tsx` | 组件/模块 | 见源码 | 见源码 |

## Visual Approval（工具 HITL 截图审批）

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `VisualApprovalInlineSection.tsx` | 入口 | 消息级 inline 审批挂载 | ✅ |
| `VisualApprovalArtifactCard.tsx` | UI | 截图 BBox + 操作区 | ✅ |
| `VisualApprovalPendingCard.tsx` | UI | snapshot loading | ✅ |
| `approval/VisualApprovalRequestRenderer.tsx` | UI | 三态路由 | ✅ |
| `approval/VisualApprovalUnavailableCard.tsx` | UI | 失败降级 + 重试 | ✅ |
| `approval/VisualApprovalHighlight.tsx` | UI | 红框 overlay | ✅ |
| `ToolApprovalDialog.tsx` | UI | modal 非 visual 审批 | ✅ |
| `MobileStatusBoard.tsx` | UI | 移动端审批面板 | ✅ |

逻辑层见 [`lib/approval/_ARCH.md`](../../lib/approval/_ARCH.md)。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
