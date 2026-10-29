# chat-window/ttft-decoupling/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DagProgressPulseTimeline.tsx` | 组件 | 导出 `DagProgressPulseTimeline` | — |
| `SpeculativeEarlyAckCard.tsx` | 组件 | 导出 `SpeculativeEarlyAckCard` | — |
| `index.ts` | 入口 | 聚合导出 `./ttftDecouplingTypes`、`./ttftDecouplingEngine`、`./useTtftDecouplingStore`、`./SpeculativeEarlyAckCard`、`./DagProgressPulseTimeline` | — |
| `ttftDecouplingEngine.ts` | 引擎 | 导出 `computeSpeculativeLatency`、`formatElapsedMs`、`analyzeCriticalPathProgress`、`groupStepsByParallelBatch`；类型 `CriticalPathAnalysisResult`、`StepBatchGroup` | — |
| `ttftDecouplingTypes.ts` | 类型 | 导出类型 `SpeculativeAckStatus`、`SpeculativeAckPayload`、`DagStepStatus`、`DagStepNode`、`DagTimelineState`、`EmitEarlyAckParams` 等 7 个 | — |
| `useTtftDecouplingStore.ts` | 状态仓库 | 导出 `useTtftDecouplingStore` | — |
| `__tests__/DagProgressPulseTimeline.test.tsx` | 测试 | `DagProgressPulseTimeline`；4 个用例 | — |
| `__tests__/SpeculativeEarlyAckCard.test.tsx` | 测试 | `SpeculativeEarlyAckCard`；2 个用例 | — |
| `__tests__/ttftDecouplingEngine.test.ts` | 测试 | `ttftDecouplingEngine`；7 个用例 | — |
| `__tests__/useTtftDecouplingStore.test.ts` | 测试 | `useTtftDecouplingStore`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
