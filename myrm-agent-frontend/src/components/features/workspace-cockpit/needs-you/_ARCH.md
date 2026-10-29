# workspace-cockpit/needs-you/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AnchoredAlertNotificationBanner.tsx` | 组件 | 导出 `AnchoredAlertNotificationBanner`；类型 `AnchoredAlertNotificationBannerProps` | — |
| `NeedsYouQueueDrawer.tsx` | 组件 | 导出 `NeedsYouQueueDrawer`；类型 `NeedsYouQueueDrawerProps` | — |
| `index.ts` | 入口 | 聚合导出 `./needsYouTypes`、`./needsYouQueueEngine`、`./useNeedsYouQueueStore`、`./NeedsYouQueueDrawer`、`./AnchoredAlertNotificationBanner` | — |
| `needsYouQueueEngine.ts` | 引擎 | 导出 `DEFAULT_OFFLINE_MERGE_WINDOW_MS`、`sortNeedsYouQueue`、`mapNeedsYouToWorkspaceTaskItems`、`deduplicateAndMergeAlerts`、`buildNeedsYouDeepLink`、`calculateQueueSummary` | — |
| `needsYouTypes.ts` | 类型 | 导出类型 `InterruptionSource`、`InterruptionUrgency`、`NeedsYouItem`、`AnchoredAlert`、`BatchActionPayload`、`NeedsYouQueueSummary` 等 7 个 | — |
| `useNeedsYouQueueStore.ts` | 状态仓库 | 导出 `useNeedsYouQueueStore`；类型 `NeedsYouQueueState` | — |
| `__tests__/AnchoredAlertNotificationBanner.test.tsx` | 测试 | `AnchoredAlertNotificationBanner`；3 个用例 | — |
| `__tests__/NeedsYouQueueDrawer.test.tsx` | 测试 | `NeedsYouQueueDrawer`；5 个用例 | — |
| `__tests__/needsYouQueueEngine.test.ts` | 测试 | `needsYouQueueEngine`；5 个用例 | — |
| `__tests__/needsYouQueueIntegration.test.tsx` | 测试 | `NeedsYouQueue Integration Flow`；1 个用例 | — |
| `__tests__/useNeedsYouQueueStore.test.ts` | 测试 | `useNeedsYouQueueStore`；6 个用例 | — |

## 依赖

- 项目内：`../workspaceCockpitTypes`
- 第三方：`lucide-react`、`react`、`zustand`
