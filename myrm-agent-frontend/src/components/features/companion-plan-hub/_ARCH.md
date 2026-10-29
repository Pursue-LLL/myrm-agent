# companion-plan-hub/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `MicroPlanDrawer.tsx` | 组件 | 导出 `MicroPlanDrawer`；类型 `MicroPlanDrawerProps` | — |
| `MiniArtifactBubble.tsx` | 组件 | 导出 `MiniArtifactBubble`；类型 `MiniArtifactBubbleProps` | — |
| `ProgressHUD.tsx` | 组件 | 导出 `ProgressHUD`；类型 `ProgressHUDProps` | — |
| `companionPlanHubEngine.ts` | 引擎 | 导出 `calculatePlanProgress`、`formatProgressHudLabel`、`toggleSubtaskSkipState`、`updateSubtaskStatus`、`formatElapsedTimeString`、`validateMicroPlanDraft` | — |
| `companionPlanHubTypes.ts` | 类型 | 导出类型 `PlanSubtaskStatus`、`PlanSubtaskItem`、`MicroPlanDraft`、`TaskExecutionProgress`、`MiniArtifactSummary`、`CompanionHubDisplayMode` 等 7 个 | — |
| `index.ts` | 入口 | 聚合导出 `./companionPlanHubTypes`、`./companionPlanHubEngine`、`./useCompanionPlanHubStore`、`./MicroPlanDrawer`、`./ProgressHUD`、`./MiniArtifactBubble` | — |
| `useCompanionPlanHubStore.ts` | 状态仓库 | 导出 `useCompanionPlanHubStore`；类型 `CompanionPlanHubStoreState` | — |
| `__tests__/MicroPlanDrawer.test.tsx` | 测试 | `MicroPlanDrawer`；6 个用例 | — |
| `__tests__/MiniArtifactBubble.test.tsx` | 测试 | `MiniArtifactBubble`；6 个用例 | — |
| `__tests__/ProgressHUD.test.tsx` | 测试 | `ProgressHUD`；5 个用例 | — |
| `__tests__/companionPlanHubEngine.test.ts` | 测试 | `companionPlanHubEngine`；6 个用例 | — |
| `__tests__/useCompanionPlanHubStore.test.ts` | 测试 | `useCompanionPlanHubStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
