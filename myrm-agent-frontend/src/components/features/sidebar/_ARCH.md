# sidebar/

## 架构概述

会话侧栏：项目、会话列表、搜索与拖拽排序。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BatchOperationBar.tsx` | 组件 | 批量操作栏：会话批量选择、移动（含 loading/toast/错误处理）、删除入口 | — |
| `ChatHistoryList.tsx` | 组件/模块 | 会话历史列表：搜索过滤、日期分组、无限滚动、DnD pin 排序、Fork/Handoff/自动化等操作编排 | — |
| `ChatHistoryRow.tsx` | 组件/模块 | 单行会话条目：右键菜单（Pin/Fork/Handoff/Automation/MoveToProject/Rename/Export/Delete）| — |
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
