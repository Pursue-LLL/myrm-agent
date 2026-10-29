# chat-window/full-duplex-bridge/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ContextualResultReanchoringCard.tsx` | 组件 | 导出 `ContextualResultReanchoringCard` | — |
| `InFlightBackgroundWorkerTray.tsx` | 组件 | 导出 `InFlightBackgroundWorkerTray` | — |
| `fullDuplexBridgeEngine.ts` | 引擎 | 导出 `calculateWorkerEta`、`formatDuration`、`calculateAggregatedProgress`、`resolveReanchorPlacement`、`generateAdoptionSnippet`；类型 `AggregatedWorkerProgress`、`ReanchorPlacementResult` | — |
| `fullDuplexBridgeTypes.ts` | 类型 | 导出类型 `BackgroundWorkerStatus`、`StepNodeStatus`、`WorkerStepNode`、`ArtifactType`、`WorkerArtifactPayload`、`BackgroundWorkerTask` 等 8 个 | — |
| `index.ts` | 入口 | 聚合导出 `./fullDuplexBridgeTypes`、`./fullDuplexBridgeEngine`、`./useFullDuplexBridgeStore`、`./InFlightBackgroundWorkerTray`、`./ContextualResultReanchoringCard` | — |
| `useFullDuplexBridgeStore.ts` | 状态仓库 | 导出 `useFullDuplexBridgeStore` | — |
| `__tests__/ContextualResultReanchoringCard.test.tsx` | 测试 | `ContextualResultReanchoringCard`；4 个用例 | — |
| `__tests__/InFlightBackgroundWorkerTray.test.tsx` | 测试 | `InFlightBackgroundWorkerTray`；4 个用例 | — |
| `__tests__/fullDuplexBridgeEngine.test.ts` | 测试 | `fullDuplexBridgeEngine`；13 个用例 | — |
| `__tests__/useFullDuplexBridgeStore.test.ts` | 测试 | `useFullDuplexBridgeStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
