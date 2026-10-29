# dockable-workbench/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DockableChangesViewer.tsx` | 组件 | 导出 `DockableChangesViewer`；类型 `DockableChangesViewerProps` | — |
| `DockableWorkbenchContainer.tsx` | 组件 | 导出 `DockableWorkbenchContainer`；类型 `DockableWorkbenchContainerProps` | — |
| `TriSurfaceTaskIndicator.tsx` | 组件 | 导出 `TriSurfaceTaskIndicator`；类型 `TriSurfaceTaskIndicatorProps` | — |
| `dockableWorkbenchEngine.ts` | 引擎 | 导出 `deriveTriSurfaceState`、`validateConnectionEpoch`、`computeDiffStats`、`DEFAULT_MOCK_CHANGES`、`DEFAULT_BOOTSTRAP_PAYLOAD` | — |
| `dockableWorkbenchTypes.ts` | 类型 | 导出类型 `DockablePanelId`、`DockPosition`、`TriSurfaceMode`、`TaskExecutionStatus`、`TriSurfaceTaskState`、`FileChangeItem` 等 8 个 | — |
| `index.ts` | 入口 | 聚合导出 `./dockableWorkbenchTypes`、`./dockableWorkbenchEngine`、`./useDockableWorkbenchStore`、`./TriSurfaceTaskIndicator`、`./DockableChangesViewer`、`./DockableWorkbenchContainer` | — |
| `useDockableWorkbenchStore.ts` | 状态仓库 | 导出 `useDockableWorkbenchStore`；类型 `DockableWorkbenchState` | — |
| `__tests__/DockableChangesViewer.test.tsx` | 测试 | `DockableChangesViewer`；4 个用例 | — |
| `__tests__/DockableWorkbenchContainer.test.tsx` | 测试 | `DockableWorkbenchContainer`；4 个用例 | — |
| `__tests__/TriSurfaceTaskIndicator.test.tsx` | 测试 | `TriSurfaceTaskIndicator`；4 个用例 | — |
| `__tests__/dockableWorkbenchEngine.test.ts` | 测试 | `dockableWorkbenchEngine`；8 个用例 | — |
| `__tests__/useDockableWorkbenchStore.test.ts` | 测试 | `useDockableWorkbenchStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
