# swarm-canvas/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ElasticSwarmCanvas.tsx` | 组件 | 导出 `ElasticSwarmCanvas`；类型 `ElasticSwarmCanvasProps` | — |
| `SoloFocusLensDrawer.tsx` | 组件 | 导出 `SoloFocusLensDrawer`；类型 `SoloFocusLensDrawerProps` | — |
| `SwarmStatusCapsuleBar.tsx` | 组件 | 导出 `SwarmStatusCapsuleBar`；类型 `SwarmStatusCapsuleBarProps` | — |
| `index.ts` | 入口 | 聚合导出 `./swarmCanvasTypes`、`./swarmCanvasEngine`、`./useSwarmCanvasStore`、`./SwarmStatusCapsuleBar`、`./ElasticSwarmCanvas`、`./SoloFocusLensDrawer` | — |
| `swarmCanvasEngine.ts` | 引擎 | 导出 `calculateSwarmSummaryStats`、`deriveAdaptiveGridColumns`、`filterWorkersByStatus`、`formatSwarmStatusCapsuleLabel`、`formatWorkerStatusBadge` | — |
| `swarmCanvasTypes.ts` | 类型 | 导出类型 `SwarmWorkerStatus`、`SwarmWorkerToolCall`、`SwarmWorkerItem`、`SwarmSummaryStats`、`WorkerSteerPayload` | — |
| `useSwarmCanvasStore.ts` | 状态仓库 | 导出 `useSwarmCanvasStore`；类型 `SwarmCanvasStoreState` | — |
| `__tests__/ElasticSwarmCanvas.test.tsx` | 测试 | `ElasticSwarmCanvas`；3 个用例 | — |
| `__tests__/SoloFocusLensDrawer.test.tsx` | 测试 | `SoloFocusLensDrawer`；5 个用例 | — |
| `__tests__/SwarmStatusCapsuleBar.test.tsx` | 测试 | `SwarmStatusCapsuleBar`；2 个用例 | — |
| `__tests__/swarmCanvasEngine.test.ts` | 测试 | `swarmCanvasEngine`；5 个用例 | — |
| `__tests__/useSwarmCanvasStore.test.ts` | 测试 | `useSwarmCanvasStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
