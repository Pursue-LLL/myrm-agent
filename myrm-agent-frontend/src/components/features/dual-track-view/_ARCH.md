# dual-track-view/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BusinessMessageCard.tsx` | 组件 | 导出 `BusinessMessageCard`；类型 `BusinessMessageCardProps` | — |
| `DualTrackModeSwitcher.tsx` | 组件 | 导出 `DualTrackModeSwitcher`；类型 `DualTrackModeSwitcherProps` | — |
| `EngineeringTraceDrawer.tsx` | 组件 | 导出 `EngineeringTraceDrawer`；类型 `EngineeringTraceDrawerProps` | — |
| `dualTrackEngine.ts` | 引擎 | 导出 `isEngineeringMessage`、`filterMessagesByViewMode`、`summarizeEngineeringTrace`、`formatTraceSummaryBadge` | — |
| `dualTrackTypes.ts` | 类型 | 导出类型 `DualTrackViewMode`、`TurnMessageKind`、`ToolCallItem`、`CodeDiffItem`、`TestAssertionItem`、`EngineeringTraceDetails` 等 9 个 | — |
| `index.ts` | 入口 | 聚合导出 `./dualTrackTypes`、`./dualTrackEngine`、`./useDualTrackStore`、`./DualTrackModeSwitcher`、`./BusinessMessageCard`、`./EngineeringTraceDrawer` | — |
| `useDualTrackStore.ts` | 状态仓库 | 导出 `useDualTrackStore`；类型 `DualTrackStoreState` | — |
| `__tests__/BusinessMessageCard.test.tsx` | 测试 | `BusinessMessageCard`；3 个用例 | — |
| `__tests__/DualTrackModeSwitcher.test.tsx` | 测试 | `DualTrackModeSwitcher`；3 个用例 | — |
| `__tests__/EngineeringTraceDrawer.test.tsx` | 测试 | `EngineeringTraceDrawer`；4 个用例 | — |
| `__tests__/dualTrackEngine.test.ts` | 测试 | `dualTrackEngine`；4 个用例 | — |
| `__tests__/useDualTrackStore.test.ts` | 测试 | `useDualTrackStore`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
