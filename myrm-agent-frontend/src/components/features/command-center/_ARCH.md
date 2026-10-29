# command-center/

## 架构概述

10 个源文件（6 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），7 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CommandCenterHeaderTrigger.tsx` | 组件 | 导出 `CommandCenterHeaderTrigger` | — |
| `CommandCenterMaintenanceTab.tsx` | 组件 | 导出 `CommandCenterMaintenanceTab` | — |
| `CommandCenterModal.tsx` | 组件 | 导出 `CommandCenterModal` | — |
| `CommandCenterSessionsTab.tsx` | 组件 | 导出 `CommandCenterSessionsTab` | — |
| `CommandCenterSystemTab.tsx` | 组件 | 导出 `CommandCenterSystemTab` | — |
| `CommandCenterUsageTab.tsx` | 组件 | 导出 `CommandCenterUsageTab` | — |
| `commandCenterEngine.ts` | 引擎 | 导出 `isCommandCenterShortcut`、`filterSessions`、`generateSessionAuditPack`、`generateDebugShareBundle`、`getDefaultSessions`、`getDefaultHealth` 等 8 个 | — |
| `commandCenterTypes.ts` | 类型 | 导出类型 `CommandCenterTab`、`HealthStatusType`、`LogComponent`、`LogLevel`、`SessionSummaryItem`、`GatewayHealthState` 等 14 个 | — |
| `index.ts` | 入口 | 聚合导出 `./commandCenterTypes`、`./commandCenterEngine`、`./useCommandCenterStore`、`./CommandCenterSessionsTab`、`./CommandCenterSystemTab`、`./CommandCenterUsageTab`、`./CommandCenterMaintenanceTab`、`./CommandCenterHeaderTrigger` 等 9 个 | — |
| `useCommandCenterStore.ts` | 状态仓库 | 导出 `useCommandCenterStore` | — |
| `__tests__/CommandCenterMaintenanceTab.test.tsx` | 测试 | `CommandCenterMaintenanceTab`；3 个用例 | — |
| `__tests__/CommandCenterModal.test.tsx` | 测试 | `CommandCenterModal`；4 个用例 | — |
| `__tests__/CommandCenterSessionsTab.test.tsx` | 测试 | `CommandCenterSessionsTab`；4 个用例 | — |
| `__tests__/CommandCenterSystemTab.test.tsx` | 测试 | `CommandCenterSystemTab`；2 个用例 | — |
| `__tests__/CommandCenterUsageTab.test.tsx` | 测试 | `CommandCenterUsageTab`；2 个用例 | — |
| `__tests__/commandCenterEngine.test.ts` | 测试 | `commandCenterEngine`；5 个用例 | — |
| `__tests__/useCommandCenterStore.test.ts` | 测试 | `useCommandCenterStore`；6 个用例 | — |
| `command-center-hud/` | 子目录 | 见 [command-center-hud/_ARCH.md](command-center-hud/_ARCH.md) | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
