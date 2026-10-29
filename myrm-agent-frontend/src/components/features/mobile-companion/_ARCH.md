# mobile-companion/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `MobileRemoteSteeringBar.tsx` | 组件 | 导出 `MobileRemoteSteeringBar`；类型 `MobileRemoteSteeringBarProps` | — |
| `MobileTaskCompanionView.tsx` | 组件 | 导出 `MobileTaskCompanionView`；类型 `MobileTaskCompanionViewProps` | — |
| `QrCodePairingModal.tsx` | 组件 | 导出 `QrCodePairingModal`；类型 `QrCodePairingModalProps` | — |
| `index.ts` | 入口 | 聚合导出 `./mobileCompanionTypes`、`./mobileCompanionEngine`、`./useMobileCompanionStore`、`./MobileRemoteSteeringBar`、`./QrCodePairingModal`、`./MobileTaskCompanionView` | — |
| `mobileCompanionEngine.ts` | 引擎 | 导出 `generatePairingConfig`、`formatTimeRemaining`、`filterHighSnrLogs`、`getPhaseBadgeInfo`；类型 `PhaseBadgeInfo` | — |
| `mobileCompanionTypes.ts` | 类型 | 导出类型 `TaskPhase`、`CompanionArtifact`、`PendingApprovalItem`、`LiveScreenshotInfo`、`MobileCompanionTask`、`PairingSessionConfig` 等 7 个 | — |
| `useMobileCompanionStore.ts` | 状态仓库 | 导出 `useMobileCompanionStore`；类型 `MobileCompanionActions`、`MobileCompanionStore` | — |
| `__tests__/MobileRemoteSteeringBar.test.tsx` | 测试 | `MobileRemoteSteeringBar`；6 个用例 | — |
| `__tests__/MobileTaskCompanionView.test.tsx` | 测试 | `MobileTaskCompanionView`；3 个用例 | — |
| `__tests__/QrCodePairingModal.test.tsx` | 测试 | `QrCodePairingModal`；4 个用例 | — |
| `__tests__/mobileCompanionEngine.test.ts` | 测试 | `mobileCompanionEngine`；4 个用例 | — |
| `__tests__/useMobileCompanionStore.test.ts` | 测试 | `useMobileCompanionStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
