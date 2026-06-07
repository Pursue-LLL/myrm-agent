# sidebar/

## 架构概述

会话侧栏：项目、会话列表、搜索与拖拽排序。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BatchOperationBar.tsx` | 组件/模块 | — | — |
| `ChatHistoryList.tsx` | 组件/模块 | — | — |
| `ChatHistoryRow.tsx` | 组件/模块 | — | — |
| `HandoffDialog.tsx` | 组件/模块 | — | — |
| `MobileDragButton.tsx` | 组件/模块 | — | — |
| `ProjectBar.tsx` | 组件/模块 | — | — |
| `Sidebar.tsx` | 组件/模块 | — | — |
| `UserMenu.tsx` | 组件 | 用户菜单（Settings、批量优化 `userMenu.batchOptimization`→`/batch-optimization`、Brain Console 等） | — |
| `constants.ts` | 组件/模块 | — | — |
| `dateGroupUtils.ts` | 组件/模块 | — | — |
| `useBatchMode.ts` | 组件/模块 | — | — |
| `useChatActions.ts` | 组件/模块 | — | — |
| `useSidebarState.ts` | 组件/模块 | — | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
