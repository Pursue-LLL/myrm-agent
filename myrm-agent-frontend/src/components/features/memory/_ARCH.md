# memory/

## 架构概述

记忆中心：浏览、编辑、归档与召回相关 UI。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ConnectWizardDialog.tsx` | 组件/模块 | — | — |
| `ConversationRecallPanel.tsx` | 组件/模块 | — | — |
| `MemoryArchiveRestoreDialog.tsx` | 组件/模块 | — | — |
| `MemoryCard.tsx` | 组件/模块 | — | — |
| `MemoryClearAllDialog.tsx` | 组件/模块 | — | — |
| `MemoryCommandCenter.tsx` | 组件/模块 | — | — |
| `MemoryCommandCenterAdvancedPanels.tsx` | 组件/模块 | — | — |
| `MemoryCommandCenterChrome.tsx` | 组件/模块 | — | — |
| `MemoryCommandCenterDoctorPanel.tsx` | 组件/模块 | — | — |
| `MemoryCommandCenterPanels.tsx` | 组件/模块 | — | — |
| `MemoryContextPanel.tsx` | 组件/模块 | — | — |
| `MemoryCreateDialog.tsx` | 组件/模块 | — | — |
| `MemoryDetailSheet.tsx` | 组件/模块 | — | — |
| `MemoryEditDialog.tsx` | 组件/模块 | — | — |
| `MemoryGuide.tsx` | 组件/模块 | — | — |
| `MemoryHealthDashboard.tsx` | 组件/模块 | — | — |
| `MemoryImportReviewDialog.tsx` | 组件/模块 | — | — |
| `MemoryKnowledgeGraph.tsx` | 组件/模块 | — | — |
| `MemorySettingsToggles.tsx` | 组件/模块 | — | — |
| `MemoryStats.tsx` | 组件/模块 | — | — |
| `MemoryTabSwitcher.tsx` | 组件/模块 | — | — |
| `MemoryTrashPanel.tsx` | 组件/模块 | — | — |
| `MemoryTypeIcon.tsx` | 组件/模块 | — | — |
| `PendingMemoryBadge.tsx` | 组件/模块 | 待审批记忆计数徽章（ChatWindow 顶栏入口，pendingCount=0 时隐藏） | onClick → openConfirmDialog |
| `PendingMemoryDialog.tsx` | 组件/模块 | 待审批记忆审批弹窗（支持编辑、批准、拒绝、来源跳转；连续审批：处理完自动显示下一条） | isConfirmDialogOpen → approve/reject |
| `PendingMemoryList.tsx` | 组件/模块 | 待审批记忆列表（含批量操作，用于 MemorySection pending tab） | showBatchActions prop |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
