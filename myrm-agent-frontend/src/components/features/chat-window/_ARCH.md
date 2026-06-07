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
| `goals/` | 目录 | Goal 控制面与 DAG 可视化 | 见下表 |

## agent-config-panel/

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentConfigPanel.tsx` | 核心 | Agent 配置面板入口 | ✅ |
| `AgentConfigEditDialog.tsx` | 核心 | Agent 编辑对话框 | ✅ |
| `TemplateMarket.tsx` | 核心 | Agent 模板市场。请求后端的 `/api/v1/agents/templates` 和 `instantiate-template` 接口，实现模板列表展示和带有原子化依赖预检的智能体实例化。 | ✅ |
| `AgentGallery.tsx` | 辅助 | Agent 画廊展示 | ✅ |

## goals/

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `GoalControlPlane.tsx` | 核心 | Goal 队列与控制面板 | ✅ |
| `GoalQueueSection.tsx` | 核心 | Goal 队列区块 | ✅ |
| `GoalStatusCard.tsx` | 核心 | 单 Goal 状态卡片 | ✅ |
| `goal-icons.tsx` | 辅助 | Goal 图标集 | ✅ |

## Visual Approval（工具 HITL 截图审批）

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `VisualApprovalInlineSection.tsx` | 入口 | 消息级 inline 审批挂载 | ✅ |
| `VisualApprovalArtifactCard.tsx` | UI | 截图 BBox + 操作区 | ✅ |
| `VisualApprovalPendingCard.tsx` | UI | snapshot loading | ✅ |
| `approval/VisualApprovalRequestRenderer.tsx` | UI | 三态路由 | ✅ |
| `approval/VisualApprovalUnavailableCard.tsx` | UI | 失败降级 + 重试 | ✅ |
| `approval/VisualApprovalHighlight.tsx` | UI | 红框 overlay | ✅ |
| `VisualApprovalOsOverlaySync.tsx` | UI | Tauri OS overlay 同步 | ✅ |
| `VisualApprovalAttentionBar.tsx` | UI | 滚动区外 pending 可达条 | ✅ |
| `approval/ShellCommandDisplay.tsx` | UI | shell 命令终端展示 + pipeline span 高亮 | ✅ |
| `SingleApprovalCard.tsx` | UI | 主 Agent 单条/批量审批卡片 | ✅ |
| `ToolApprovalDialog.tsx` | UI | modal 非 visual 审批 | ✅ |
| `MobileStatusBoard.tsx` | UI | 移动端审批面板 | ✅ |

逻辑层见 [`lib/approval/_ARCH.md`](../../lib/approval/_ARCH.md)。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
